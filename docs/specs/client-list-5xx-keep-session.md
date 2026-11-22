# Spec — Garder la session sur un 5xx de `client_list`

- **Statut :** proposition (spec seule, aucun changement de code dans cette PR)
- **Date :** 2026-11-22
- **Composants :** `custom_components/tplink_deco/api.py`, `coordinator.py`, `tests/`
- **Garde-fous concernés :** [FORK-SAFEGUARDS](../FORK-SAFEGUARDS.md) A (anti-churn), A4, B3, C1

## 1. Contexte

### Incident du 2026-11-22 à 19:00 (HA PROD Roquefort, v3.15.2.1)

Six minutes après un redémarrage de Home Assistant, un cycle de polling clients a reçu un
HTTP 502 sur le `client_list` par nœud de trois Decos sur quatre (le Deco salon a répondu) :

```
2026-11-22 19:00:46.467 WARNING [custom_components.tplink_deco.api] List Clients 28-87-BA-B2-B0-00 server error 502, clearing auth for retry
2026-11-22 19:01:02.159 WARNING [custom_components.tplink_deco.api] List Clients 28-87-BA-B2-8C-58 server error 502, clearing auth for retry
2026-11-22 19:01:19.191 WARNING [custom_components.tplink_deco.api] List Clients 28-87-BA-B2-8C-00 server error 502, clearing auth for retry
```

Observations :

- Chaque 502 a appelé `clear_auth()`. Le nœud suivant a donc refait un login complet :
  **3 nouvelles sessions admin dans le même cycle**, soit l'inverse de la règle anti-churn (A).
- Le cycle a duré **49 s** au lieu de ~24 s (médiane sur 3 jours ; `client_api_response_time`).
- La présence n'a pas été affectée : le coordinator a gardé l'état précédent des clients des
  Decos en échec (C1), et le cycle suivant (19:06) était propre. Aucun 502 dans les 24 h
  précédentes.
- Hypothèse : juste après le redémarrage de HA, la table de sessions du Deco contenait encore
  les anciennes sessions en plus de la nouvelle. Le master n'a pas pu relayer `client_list` vers
  les nœuds (502 = Bad Gateway côté Deco). Re-logger à chaque 502 ajoute des sessions
  au moment précis où le Deco est saturé.

### Règle anti-churn (FORK-SAFEGUARDS, section A)

> Le firmware Deco a peu de sessions admin. Chaque re-login en crée une ; trop de re-logins
> → le Deco ralentit puis ne répond plus (vécu en prod). On ne vide la session (`clear_auth`)
> **que** lorsqu'elle est réellement invalide.

Un 502 sur `client_list` d'un nœud ne prouve pas que la session est invalide : les autres
nœuds du même cycle répondent avec la même session (ici, le Deco salon).

## 2. Comportement actuel

- `api.py` `_async_post`, branche `aiohttp.ClientResponseError` (~l. 959-990) :
  - pour `form=client_list` avec un 5xx, le message est déjà rétrogradé en `debug` (~l. 960-967) ;
  - mais ensuite, **tout** 5xx passe par :
    ```python
    if err.status >= 500:
        # Server error (502 Bad Gateway, etc.) — clear auth and retry
        self.clear_auth()
        _LOGGER.warning("%s server error %s, clearing auth for retry", context, err.status)
    raise err
    ```
    (~l. 984-990). `_async_call_with_retry_inner` ne réessaie pas les `ClientResponseError` :
    le `clear_auth()` ne sert donc qu'à forcer un login sur **l'appel suivant**, c.-à-d. le nœud
    suivant du même cycle.
- `coordinator.py` `_async_list_clients_per_deco` (~l. 707-739) : un 5xx par nœud est absorbé
  (`failed_deco_macs`) ; si tous les nœuds échouent, repli global puis backoff 30-300 s (B3).
- `coordinator.py` ~l. 968 : les clients d'un Deco en échec gardent leur dernier état (C1).
- Garde-fou A4 (« `clear_auth` seulement sur 401 / 403 / 5xx ») et ses tests
  `test_async_post_502_clears_auth`, `test_authenticated_http_500_clears_auth_session`.

## 3. Comportement proposé

1. **5xx sur `client_list` (par nœud ou global) → session gardée.** Pas de `clear_auth()`.
   On lève l'erreur telle quelle ; le coordinator la gère déjà (nœud en échec, repli global,
   backoff). Log `debug` par nœud ; le résumé `warning` reste celui du coordinator
   (`Client list query returned HTTP …; backing off …`), émis une fois par série.
2. **Re-auth conservée pour une session réellement invalide :**
   - 401 / 403 (inchangé) ;
   - `error_code=-5002` sur une réponse authentifiée (A7, inchangé) ;
   - réponse vide ou indécodable (A3, inchangé) ;
   - **5xx sur un appel du master** (`device_list`, `fetch keys` / login, `performance`,
     `wireless`, `system_log`…) : `clear_auth()` conservé (A4 restreint à ces appels).
3. **Escalade bornée** : si `client_list` renvoie un 5xx sur **tous** les nœuds **et** au repli
   global pendant N cycles consécutifs (proposition N = 3, constante
   `CLIENT_LIST_5XX_REAUTH_AFTER_CYCLES`), le coordinator demande **un** `clear_auth()` unique
   avant le cycle suivant (une session au plus par série), puis reprend le backoff B3.
   Ça couvre le cas d'une session expirée que le firmware signalerait par un 5xx.
4. Message `warning` d'`api.py` réservé aux 5xx qui vident la session (master), avec un texte
   qui le dit : `"%s server error %s, clearing auth"` (le « for retry » est trompeur : il n'y a
   pas de retry immédiat).

## 4. Cas limites

| Cas | Comportement attendu |
| --- | --- |
| 1 à 3 nœuds en 5xx, au moins un nœud OK | Session gardée, nœuds en échec dans `failed_deco_macs`, leurs clients gardent leur état (C1). 0 login. |
| Tous les nœuds en 5xx, repli global OK | Session gardée, mode `global_fallback`, re-sonde par nœud à 300 s (B3). 0 login. |
| Tous les nœuds + global en 5xx (une fois) | Session gardée, backoff 30 s (B3), présence préservée. 0 login. |
| 5xx persistant (≥ N cycles complets) | Un seul `clear_auth()` → un login au cycle suivant ; si le 5xx continue, le backoff monte jusqu'à 300 s, **pas** de nouveau login avant N nouveaux cycles. Au plus 1 session / N cycles. |
| Session réellement expirée signalée par un 5xx | Récupérée par l'escalade (point 3) ou plus tôt par le premier appel master du cycle `device_list` (5xx master → `clear_auth`, ou -5002/401/403). Délai max ≈ N × intervalle. |
| Session expirée signalée par -5002 / 401 / 403 / réponse vide | Inchangé (A3, A4, A7) : `clear_auth` + re-login. |
| Reboot du Deco | Inchangé : `ClientConnectorError`/timeout gardent la session (A1, A2), la session périmée est ensuite rejetée par -5002/401/403/vide. |
| 5xx sur `device_list` / login | Inchangé : `clear_auth()` (A4 restreint). |

## 5. Plan de test

Nouveaux tests (mock `aiohttp`, style `tests/test_api_transport_errors.py` / `test_coordinator.py`) :

1. `test_client_list_5xx_keeps_auth` : `_async_post` avec `form=client_list` → 502 :
   `ClientResponseError` levée, `_stok`/cookie **conservés**, aucun log `warning` d'`api.py`.
2. `test_per_node_5xx_cycle_does_not_relogin` : 4 nœuds, 3 en 502 et 1 OK → **0** POST de login
   pendant le cycle ; les clients des 3 nœuds gardent leur état.
3. `test_all_nodes_and_global_5xx_keeps_auth_then_escalates_once` : N cycles 100 % 5xx →
   exactement **1** `clear_auth()` puis 1 login, pas plus pendant les N cycles suivants.
4. `test_device_list_5xx_still_clears_auth` : 5xx sur `device_list` → `clear_auth()` (A4 restreint).
5. Non-régression : `test_async_post_403_clears_auth`, A7 (-5002), A3 inchangés.

Tests existants à adapter : `test_async_post_502_clears_auth` et
`test_authenticated_http_500_clears_auth_session` doivent viser un endpoint master (pas
`client_list`). Mettre à jour la ligne A4 de `docs/FORK-SAFEGUARDS.md` (« `clear_auth` sur
401 / 403 / 5xx **hors `client_list`** ; `client_list` 5xx → session gardée, escalade après N
cycles ») et le contrôle n° 3 de la checklist de sync, **dans la même PR** (règle AGENTS.md).

Couverture : le dépôt impose 100 % (`setup.cfg`).

## 6. Déploiement

1. PR d'implémentation séparée, relue (Entire Code review + CI verte, couverture 100 %).
2. Release fork `3.15.2.2` via le skill `ha-tplink-deco-release` (changelog README).
3. Déploiement HA PROD après le go de René, avec un redémarrage groupé.
4. Vérification 24 h : aucun log `clearing auth` sur `client_list` ; nombre de logins par jour
   (debug `Received new sysauth session cookie`) en baisse ; `client_api_response_time` sans pic
   > 45 s ; aucun faux « absent ».
5. Retour arrière : revenir à `3.15.2.1` (seul `api.py`/`coordinator.py` changent ; pas de migration
   de config).
6. Upstream : proposer à `amosyuen/ha-tplink-deco` dans `upstream-prs/` (même format que
   `keep-session-on-transport-errors.md`) une fois validé en prod.
