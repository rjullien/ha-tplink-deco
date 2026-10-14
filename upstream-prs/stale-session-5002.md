Title: Recover on -5002 session expiry mid-use

## Summary

Follow-up to #598 (review comment by @dkwolf1): `error_code=-5002` is handled during login but not on an already-authenticated response. If a Deco expires the session mid-use, `_async_post` raises `UnexpectedApiException` without clearing auth, so the integration keeps a dead session forever.

This change treats an authenticated `-5002` the same as an empty response: `clear_auth()` + `EmptyDataException`, so the existing retry performs exactly one re-login. It is placed in the shared response check, so it covers both the standard LuCI session and the Deco S7 outer session (same failure mode, e.g. the S7 reboot scenario from #598).

**Change:** 7 lines in `api.py`, plus 3 regression tests in `tests/test_api_transport_errors.py`. No behaviour change for other error codes.

**Tests** (mocked `aiohttp` session; all 3 fail on current `main`, all pass with this change):

- LuCI: `-5002` on an authenticated call → auth cleared, `EmptyDataException` raised
- LuCI: `async_list_devices` with `-5002` then success → retried with exactly **1** re-login
- Outer (S7): `-5002` on a stale outer session after a connector error → exactly **1** outer login, recovery with the fresh session

```bash
pip install -r requirements.txt pycryptodome pytest pytest-asyncio
PYTHONPATH=. pytest --no-cov tests/
```

**Honesty note:** `-5002` after login was not observed during testing (per the #598 discussion and pmoranga's S7 test), so this is defensive hardening for a recovery path that otherwise cannot recover — not a confirmed production bug fix.
