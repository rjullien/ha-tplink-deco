# Upstream readiness analysis for FORK-SAFEGUARDS.md

**Reviewed with Laurine on Monday 12 October 2026 morning.**

@cursor Please update `docs/FORK-SAFEGUARDS.md` in this same branch to enrich it with the analysis below. Do not change the safeguard definitions themselves yet; add a new section (e.g. "## Upstream readiness") that records the conclusions. The goal is to decide, item by item, which fork safeguards are worth proposing upstream to amosyuen/ha-tplink-deco and which are fork-specific.

## Context

This fork (`rjullien/ha-tplink-deco`) runs on a real home mesh: 1 master XE75Pro + 3× X50 (4 Decos total). The safeguards in sections A–D were added to fix real production incidents. Before any upstream proposal, each item should be evaluated on universality vs. specificity.

## Items to challenge / reframe

### B3 — per-node client_list with timeout_error_retries=0 + global fallback + re-probe every 300s

**Current angle in the doc:** optimization for a 4-node mesh.
**New angle to record:** scaling. With many Decos (the doc should mention the 50-Deco hypothetical), per-node queries without timeout retries avoid multiplying latency and load across the mesh. Decos are increasingly loaded by dense Wi-Fi client counts, so fewer, leaner API calls keep the firmware responsive.
**Selling point for upstream:** frame it as a scaling strategy, not a personal config tweak. The partial-failure behavior is already protected by C1 (failed nodes keep last-known client state), so losing one node's clients for one cycle has limited impact.
**Risk to note:** zero retries means an isolated timeout on a distant node drops its clients for that cycle; argue that C1 mitigates this.

### B4 — extended polling intervals 180/240/300s

**Upstream risk:** amosyuen's integration offers 10/30/60/120s. Adding 180/240/300 is a product choice tied to this fork's production load; the maintainer may see it as unnecessary complexity in the select entity without universal benefit.
**Action:** flag as "fragile for upstream", keep in fork unless strong community demand.

### C4 — restore disconnected trackers at startup via async_get_stored_state (HA ≥ 2026.11) with last_states fallback

**Upstream risk:** depends on a Home Assistant version that may not be released yet at proposal time. Risky for a mainstream integration to require an unreleased API.
**Action:** flag as "fragile for upstream"; propose only after the HA version is actually released and stable.

### D4 — CoordinatorHealth sensors (api_response_time, last_error, client_timeouts) used by owner's CRM alerts

**Verdict:** fork-specific. These are internal supervision metrics; a typical user wants devices and clients, not request timings. amosyuen already ships a standard diagnostics dump (diagnostics.py) with secrets redacted, which covers the on-demand case. Visible always-on health sensors are a nice-to-have for power users but not a core expectation.
**Action:** do NOT propose upstream as-is. If ever proposed, reframe as an optional diagnostics enhancement, clearly separated from core functionality.

## Items considered safe to propose upstream

- **A1–A6** (session anti-churn): universal value, prevents Deco session table exhaustion on any firmware with few admin sessions. A6 (clear_auth also clears RSA keys and outer session) is especially relevant for S7-like firmwares.
- **B1** (request lock): universal, prevents parallel/bursty API hammering.
- **B2** (2s transient retry backoff under lock): universal.
- **C1–C3** (presence retention on partial failure, consider_home, empty-decos fallback): universal reliability improvements.
- **D1** (performance endpoint failure must not fail the refresh): universal.
- **D2** (kilobits_to_kilobytes + coerce_float): universal correctness fix.
- **D3** (check_data_error_code on all responses incl. outer): universal.
- **D5** (http→https upgrade on 307 redirect): universal, works around aiohttp ≥ 3.14 cookie drop.
- **D6** (never log sysauth/stok, redacted diagnostics): universal security.

## Which safe items merit an issue before the PR

Not every safe item needs an issue. Two stand out as behavior-changing enough that discussing first is wise:

### A5 — async_logout on unload under the lock with signed payload

**Why an issue first:** this is a behavior change to session lifecycle (the integration starts actively logging out), similar to the Livebox case where cyr-ius replaced the integration-side approach with a library-level one. An issue lets the maintainer weigh in on whether logout belongs in the integration or should be pushed to a lower layer, before code is written.

### D5 — http→https permanent upgrade on 307 redirect

**Why an issue first:** this is a workaround for an aiohttp ≥ 3.14 bug (cookie dropped on redirect). It may interact with upstream's own HTTP/HTTPS handling or with future aiohttp fixes, so confirming the approach with the maintainer avoids a PR that gets bikeshedded or rejected for touching connection logic.

All other safe items (A1–A4, A6, B1, B2, C1–C3, D1–D3, D6) are pure fixes with clear universal value: open the PR directly.

## Suggested next step

After updating this file, open a draft PR to amosyuen/ha-tplink-deco proposing B3 (reframed as scaling) and the A/C/D items marked safe, while explicitly keeping B4, C4, and D4 as fork-only for now. For A5 and D5, open issues first to validate the approach.
