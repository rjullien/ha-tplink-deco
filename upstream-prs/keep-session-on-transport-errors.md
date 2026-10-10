Title: Keep Deco session on transient transport errors

## Summary

`_async_post` currently calls `clear_auth()` on `aiohttp.ServerDisconnectedError` (added in #590) and on `aiohttp.ClientConnectorError`. After a short network hiccup, the retry or the next update therefore performs a full login, which opens a new admin session on the Deco, although the existing `stok`/cookie is usually still valid.

This PR keeps the auth state on these transport errors. The `ClientConnectorError` case was added in #142 to recover after a Deco reboot; that recovery is still covered, because a stale session is rejected on the next call (401/403, `-5002`, or empty data) and those paths already call `clear_auth()` and log in again.

**Change:** two `clear_auth()` calls removed in `api.py` (+1 −4), plus regression tests in `tests/test_api_transport_errors.py`. No behaviour change for HTTP errors.

**Tests** (mocked `aiohttp` session; 3 of them fail on current `main`, all 5 pass with this change):

- `ServerDisconnectedError` / `ClientConnectorError`: auth kept (currently cleared)
- `async_list_devices` with one disconnect then success: retried with **0** login posts (currently 1)
- `ClientPayloadError`: auth kept (unchanged)
- 403: auth cleared and exactly one re-login (unchanged)

The repo has no test setup yet, and `setup.cfg` enforces 100 % coverage, so run them without the coverage gate:

```bash
pip install -r requirements.txt pycryptodome pytest pytest-asyncio
PYTHONPATH=. pytest --no-cov tests/
```

Pre-commit passes. I'm happy to drop the test file if you'd rather keep the PR to the `api.py` change.

Real-world check: my fork runs this behaviour on a 4-node mesh (XE75 Pro + 3× X50, ~80 clients, per-node mode). On 2026-10-08 the master rebooted (`TimeoutException`, then `ClientConnectorError` while it was down); the integration recovered on the first update after the Deco came back, with no manual action.

Possibly related to #555 (X50: timeouts followed by 403 on login / "invalid credentials"), where repeated re-logins could exhaust the Deco session table — I could not confirm this on that setup.
