# Log out of the Deco when the config entry is unloaded

## Summary

Upstream does not log out when a config entry is unloaded or reloaded, leaving
the admin session open on the Deco until it times out. Repeated reloads can
therefore leave sessions allocated. This behavior has not been verified on
hardware.

## Change

After all platforms unload successfully, shut down the Deco and client
coordinators before logging out. The API sends a best-effort authenticated
logout under `_operation_lock`, then clears local authentication state even if
the request fails. A logout failure does not block unload; a failed platform
unload keeps the session.

The endpoint and payload match the Deco client in `tplinkrouterc6u` 5.38.0
(`client/deco.py`): `admin/system?form=logout` with
`{"operation": "logout"}`. The equivalent call has shipped in the fork since
v3.9.1.0, the first release tag containing `async_logout`. Fork history shows
two introduction commits, `35f03f9` and `5c45857` (both 2026-05-29). The
v3.9.1.0 README changelog records request serialization and the session-churn
fix; v3.10.5.0 later names `async_logout` explicitly.

## Tests

On upstream `main`, before the implementation:

```text
4 failed, 1 passed
```

With the implementation:

```text
5 passed
```

Full upstream suite:

```text
79 passed, 7 warnings
```

All pre-commit hooks pass.

Tests: `test_async_logout_posts_logout_and_clears_auth`,
`test_async_logout_without_session_does_not_call_router`,
`test_async_logout_failure_still_clears_auth`,
`test_unload_entry_logs_out_after_platforms_unload`, and
`test_unload_entry_failed_platform_unload_keeps_session`.

## Diff stat

`git diff --stat upstream/main...upstream/logout-on-unload`:

```text
 custom_components/tplink_deco/__init__.py |   6 ++
 custom_components/tplink_deco/api.py      |  18 ++++
 tests/test_unload_logout.py               | 155 ++++++++++++++++++++++++++++++
 3 files changed, 179 insertions(+)
```
