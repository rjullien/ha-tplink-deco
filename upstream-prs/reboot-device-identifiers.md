## Summary

Follow-up to #521 (one of its remaining items, submitted individually as requested by @dkwolf1).

The `reboot_deco` service crashes when the selected device does not have **exactly one** registry identifier:

```python
id = next(iter(ids)) if len(ids) == 1 else None
if id[0] != DOMAIN:  # TypeError: 'NoneType' object is not subscriptable
```

- `len(ids) > 1` (a device can carry extra identifiers, e.g. after a rename or an integration overlap): `id` is `None` → `id[0]` raises `TypeError` instead of rebooting — even when a valid `(DOMAIN, mac)` identifier is present.
- `len(ids) == 0`: same crash instead of the intended clear error.

### Change

New helper `deco_mac_from_identifiers()` returns the `(DOMAIN, mac)` identifier however many identifiers the device has, or `None`. The service now fails with the clear "does not have tplink_deco MAC identifier" error only when no Deco identifier exists.

`__init__.py`: +8/−4, plus `tests/test_device_identifiers.py` (3 tests: single identifier, Deco identifier among several, no Deco identifier → `None`). The tests error out on current main (helper absent); all pass with the change.

```
pip install -r requirements.txt pycryptodome pytest pytest-asyncio
PYTHONPATH=. pytest --no-cov tests/
```
