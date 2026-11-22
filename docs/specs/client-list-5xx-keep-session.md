# Spec — Garder la session sur un 5xx de `client_list`

- **Statut :** implémentée dans cette PR (`api.py` `_async_post`, tests, A4 de `FORK-SAFEGUARDS.md`)
- **Date :** 2026-11-22 (révisée le même jour après analyse des logs et de l'historique HA)
- **Composants :** `custom_components/tplink_deco/api.py`, `tests/`, `docs/FORK-SAFEGUARDS.md`
- **Garde-fous concernés :** [FORK-SAFEGUARDS](../FORK-SAFEGUARDS.md) A (anti-churn), A4, B3, C1

## 1. Incident du 2026-11-22 (HA PROD Roquefort, v3.15.2.1)

Heures de Paris (logs Core). L'historique HA est en UTC (+1 h).

| Heure    | Fait observé                                                                                                       |
| -------- | ------------------------------------------------------------------------------------------------------------------ |
| 18:53    | Redémarrage de Home Assistant.                                                                                     |
| 18:54:12 | `Fetch keys: Router redirected to HTTPS, switching host to https://10.182.207.1` : l'intégration passe en HTTPS.   |
| 19:00:30 | Début d'un cycle clients par nœud.                                                                                 |
| 19:00:46 | `List Clients 28-87-BA-B2-B0-00 server error 502, clearing auth for retry` (ChambreParents, X50, satellite).       |
| 19:01:02 | `List Clients 28-87-BA-B2-8C-58 server error 502, clearing auth for retry` (Living Room, X50, satellite).          |
| 19:01:19 | `List Clients 28-87-BA-B2-8C-00 server error 502, clearing auth for retry` (ChambreCamille, X50, satellite).       |
| 19:01:19 | Fin du cycle : 49 s (`client_api_response_time`) au lieu de ~24 s.                                                 |
| 19:14:48 | Reload de l'intégration après passage de l'URL à `https://10.182.207.1` dans les options. Cycles suivants propres. |

Faits vérifiés :

- Le seul nœud qui a répondu est le **master Kitchen (XE75Pro, `7C-F1-7E-E4-AC-92`)**. Les
  **trois satellites** ont renvoyé 502.
- Les 502 sont arrivés **en HTTPS** : l'intégration avait déjà basculé d'elle-même à 18:54:12.
  Le changement d'URL de 19:14 n'a fait qu'aligner la configuration sur ce comportement (fin de
  l'avertissement de redirection). Il n'explique pas l'absence de 502 depuis.
- Après le premier 502, `clear_auth()` a forcé un login complet avant chacun des deux satellites
  suivants, qui ont **quand même** renvoyé 502. Le re-login n'a rien réparé.
- Chaque appel en échec a pris 16 à 17 s, contre ~6 s par nœud en temps normal.
- Présence : aucun des 105 trackers routeur n'a changé d'état pendant ce cycle (C1). Au reload de
  19:14:48, tous sont passés `unavailable` 12 s puis sont revenus à leur état précédent.
- Aucun autre 502 dans les logs Core retenus (depuis le 2026-11-21 20:10) ni après l'incident.
- Le Deco est resté lent environ 50 min après le redémarrage, avec ou sans 502 :
  29 s, 49 s (502), 36 s, 45 s, puis après le reload 36 s, 31 s, 28 s, 28 s, 26 s, 24 s.
  Après le redémarrage du 2026-11-20, aucun ralentissement (28 s puis 25 s).

Diagnostic :

- **502 = Bad Gateway** : le master répond lui-même, mais n'obtient pas la réponse du satellite
  qu'il relaie. Le délai de 16-17 s est cohérent avec un relais qui attend puis abandonne
  (déduction : les logs debug n'étaient pas actifs).
- **La session n'est pas en cause** : le master a répondu avec cette session, et deux sessions
  neuves ont échoué de la même façon.
- **Cause du ralentissement après redémarrage : inconnue.** Piste non prouvée : au redémarrage de
  HA l'intégration ne se déconnecte pas (logout seulement à l'unload, A5), l'ancienne session
  reste donc ouverte sur le Deco. Hors périmètre de cette spec.

## 2. Comportement actuel

- `api.py` `_async_post`, branche `aiohttp.ClientResponseError` : pour `form=client_list` un 5xx
  est déjà journalisé en `debug`, mais **tout** 5xx finit par :
  ```python
  if err.status >= 500:
      # Server error (502 Bad Gateway, etc.) — clear auth and retry
      self.clear_auth()
      _LOGGER.warning("%s server error %s, clearing auth for retry", context, err.status)
  raise err
  ```
  `_async_call_with_retry_inner` ne réessaie pas les `ClientResponseError` : le `clear_auth()`
  force seulement un login sur **l'appel suivant**, c.-à-d. le nœud suivant du même cycle.
- `coordinator.py` `_async_list_clients_per_deco` : un 5xx par nœud est absorbé
  (`failed_deco_macs`) ; si tous les nœuds échouent, repli global puis backoff 30-300 s (B3).
- Les clients d'un Deco en échec gardent leur dernier état (C1).

## 3. Comportement proposé (version minimale)

Une seule règle, dans `api.py` `_async_post` :

1. **5xx sur `form=client_list` → session gardée**, quel que soit le nœud (satellite, master ou
   appel global) : pas de `clear_auth()`, l'erreur est levée telle quelle. Le coordinator la gère
   déjà (nœud en échec, repli global, backoff B3).
2. Ce cas garde **un** log `warning` par appel, pour que les incidents restent visibles en prod :
   `"%s server error %s, keeping session"`.
3. **Tout le reste est inchangé :**
   - 5xx sur les autres appels (`device_list`, clés/login, `performance`, `wireless`,
     `system_log`, …) → `clear_auth()` et log actuel ;
   - 401 / 403 → `clear_auth()` (A4) ;
   - `error_code=-5002` sur une réponse authentifiée → `clear_auth()` puis re-login (A7) ;
   - réponse vide ou indécodable → A3 ;
   - erreurs de transport → session gardée (A1, A2).

Aucun changement dans `coordinator.py`, pas de nouvelle constante, pas de nouvel état.

### Escalade bornée : retirée

La première version prévoyait un `clear_auth()` après N cycles 100 % en 5xx. Elle est retirée :

- **Inutile** : le coordinator Deco interroge `device_list` sur le master à chaque
  `device_list_interval` (en prod, environ toutes les 5 min). Une session réellement invalide y
  est détectée (-5002, 401/403, réponse vide, ou 5xx → `clear_auth()` inchangé) et le re-login se
  fait comme aujourd'hui.
- **Risquée** (relecture Devin Review de cette PR) : `failed_deco_macs` mélange 5xx, timeouts et
  erreurs de connexion ; le repli à 300 s rend « N cycles » mal défini ; un `clear_auth()` lancé
  par le coordinator se ferait hors du verrou des requêtes ; la limite « 1 login par série » vs
  « 1 login tous les N cycles » était contradictoire.

## 4. Cas limites

| Cas                                                                | Comportement attendu                                                                                          |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| 1 à 3 satellites en 5xx, master OK (cas du 22/11)                  | Session gardée, satellites dans `failed_deco_macs`, leurs clients gardent leur état (C1). 0 login.            |
| Tous les nœuds en 5xx, repli global OK                             | Session gardée, mode `global_fallback`, re-sonde par nœud à 300 s (B3). 0 login.                              |
| Tous les nœuds + global en 5xx                                     | Session gardée, backoff B3, état des clients conservé. 0 login.                                               |
| 5xx sur `client_list` du master seul                               | Session gardée (même règle). `device_list` du cycle Deco vérifie la session.                                  |
| Session réellement expirée                                         | Détectée par -5002 / 401 / 403 / réponse vide sur n'importe quel appel, ou 5xx sur `device_list`. Inchangé.   |
| 5xx sur `device_list` / clés / login                               | Inchangé : `clear_auth()` (A4 restreint).                                                                     |
| Reboot du Deco                                                     | Inchangé : A1, A2, A3, A7.                                                                                    |
| Panne partielle longue (≥ 10 clients en ligne avant, < 20 % reçus) | Inchangé et hors périmètre : après 30 min la liste partielle est acceptée (liste suspecte, `coordinator.py`). |

Limite acceptée : un firmware qui signalerait une session expirée **uniquement** par un 5xx sur
`client_list`. Jamais observé. Une session expirée signalée par -5002, 401/403 ou une réponse vide
sur `client_list` reste détectée par ce même appel (A3, A4, A7). Avec `device_list_interval: 0`,
`device_list` n'est plus interrogé après le démarrage : la vérification périodique décrite au §3 ne
s'applique pas, seule cette détection par `client_list` reste. Dans le cas limite, le comportement
serait celui d'une panne de relais (C1 + B3), sans faux « absent » immédiat.

## 5. Plan de test

Nouveaux tests (style `tests/test_api_client.py`, `tests/test_api_transport_errors.py`,
`tests/test_coordinator.py`) :

1. `test_client_list_http_500_keeps_auth_session` et
   `test_consecutive_client_list_502_do_not_relogin` : `_async_post` avec
   `params={"form": "client_list"}` et 5xx → `ClientResponseError` levée, `_stok` et cookie
   **conservés**, un log `warning` `keeping session` ; deux appels satellite successifs ne
   déclenchent pas de re-login.
2. `test_per_node_5xx_cycle_does_not_relogin` : master OK + 3 satellites en 502 → **0** login
   pendant le cycle ; les clients des 3 satellites gardent leur état.
3. Non-régression A4 restreint : `test_device_list_http_502_clears_auth`,
   `test_async_post_502_clears_auth` (endpoint hors `client_list`, inchangé) et
   `test_async_post_403_clears_auth` restent verts.

Test existant adapté : `test_authenticated_http_500_clears_auth_session` visait `client_list` ;
il a été renommé `test_client_list_http_500_keeps_auth_session`, l'assertion sur la session a
été inversée et la vérification que les logs ne contiennent ni `stok` ni `sysauth` est conservée.

Dans la **même PR** que le code (règle `AGENTS.md`) :

- ligne A4 de `docs/FORK-SAFEGUARDS.md` :
  « `clear_auth` sur 401 / 403 / 5xx, **sauf 5xx sur `client_list` : session gardée** »,
  avec les tests ci-dessus ;
- contrôle n° 3 de la checklist de sync : « … (401/403/5xx hors `client_list`, logout, session
  expirée, outer invalide) ».

Couverture : le seuil du dépôt est `fail_under = 75` (`setup.cfg`) ; les nouvelles lignes
doivent être couvertes par les tests ci-dessus.

## 6. Déploiement

1. PR d'implémentation séparée, relue (revue automatique + CI verte).
2. Release fork `3.15.2.2` via le skill `ha-tplink-deco-release` (changelog README).
3. Déploiement HA PROD après le go de René, sans redémarrage ; chargé au prochain redémarrage.
4. Vérification : plus de `clearing auth` sur `List Clients` ; en cas de 502, un log
   `keeping session` par satellite et aucun login entre eux ; `client_api_response_time` sans pic
   inexpliqué ; aucun faux « absent ».
5. Retour arrière : revenir à `3.15.2.1` (seul `api.py` change, pas de migration de config).
6. Upstream : proposition éventuelle à `amosyuen/ha-tplink-deco` après validation en prod, une
   seule à la fois (règle du tableau `Upstream contributions`).
