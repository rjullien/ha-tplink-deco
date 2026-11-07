# Deco device payload without a nickname

Title: Handle a Deco without nickname in device_list

## Summary

`TpLinkDeco.update()` raises `AttributeError: 'NoneType' object has no attribute 'split'` when a `device_list` entry has neither `custom_nickname` nor
`nickname`: `snake_case_to_title_space(None)` calls `.split()` on `None`. The
same bug was listed in #521 (closed unmerged), so it is still present on
`main`. It has not been observed on our hardware (all our Decos report a
nickname): this is a defensive fix.

## Change

- An empty `custom_nickname` is treated like a missing one and falls back to
  `nickname`.
- Without either, the Deco is named after its MAC address instead of staying
  `None`. Leaving `None` would only move the problem: `device.py` builds the
  registry name as `f"{deco.name} Deco"` ("None Deco") and `sensor.py` uses
  `deco.name` as the sensor name prefix.

## Tests

`tests/test_deco_nickname.py`: no nickname → MAC name; `nickname` is formatted
(`living_room` → `Living Room`); `custom_nickname` wins over `nickname`; an
empty `custom_nickname` falls back to `nickname`, then to the MAC; the device
registry name is `<MAC> Deco` without a nickname.

Against upstream `main` before the fix:

```text
4 failed, 2 passed, 1 warning in 1.92s
```

With the fix, full suite:

```text
80 passed, 1 warning in 2.38s
```

## Diff stat

`git diff --stat upstream/main...fix/deco-without-nickname`:

```text
 custom_components/tplink_deco/coordinator.py | 13 ++++---
 tests/test_deco_nickname.py                  | 55 ++++++++++++++++++++++++++++
 2 files changed, 63 insertions(+), 5 deletions(-)
```
