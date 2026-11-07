# Deco device payload without a nickname

## Summary

`TpLinkDeco.update()` raises an `AttributeError` when a `device_list` payload has
neither `custom_nickname` nor `nickname`: `snake_case_to_title_space(None)`
attempts to call `.split()` on `None`. This is a defensive fix for payloads
without `nickname`, as reported in the older #521. It has not been observed on
our hardware: all four of our Decos report a nickname.

## Change

Only derive the default Deco name when `nickname` is present. If both nickname
fields are absent, `name` stays `None`. `device_tracker.py` already handles
that with `if self._deco.name is not None`. The device-registry name expression
in `device.py` (`f"{deco.name} Deco"`) is unchanged and out of scope.

## Tests

Against upstream `main` before the fix, the new tests reproduce the bug:

```text
1 failed, 2 passed
```

With the fix:

```text
3 passed
```

Full upstream suite:

```text
77 tests collected; 77 passed, 7 warnings (exit code 0)
```

## Diff stat

`git diff --stat upstream/main...upstream/deco-without-nickname`:

```text
 custom_components/tplink_deco/coordinator.py |  4 +++-
 tests/test_deco_nickname.py                  | 29 ++++++++++++++++++++++++++++
 2 files changed, 32 insertions(+), 1 deletion(-)
```
