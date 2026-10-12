# Decrypt failure on invalid outer session after Deco reboot

@cursor Please review this analysis and implement the unit test described in section 3, then open a PR against amosyuen/ha-tplink-deco.

## 1. Context

PR #598 on amosyuen/ha-tplink-deco ("Keep Deco session on transient transport errors") removes `clear_auth()` from the `ServerDisconnectedError` and `ClientConnectorError` handlers in `custom_components/tplink_deco/api.py` `_async_post`. Auth is now only cleared when a subsequent call returns HTTP 401 or 403.

Maintainer dkwolf1 asked for one more test case: a Deco S7 reboot that invalidates the encrypted outer session **without** returning 401/403. The Deco may respond with HTTP 200 and encrypted payload that can no longer be decrypted with the stored AES key/IV.

## 2. Current behavior gap

- `_decrypt_data()` raises a generic exception (ValueError / cryptography padding error) when decryption fails.
- That exception is not handled as an auth failure: it is not caught in `_async_post` or `_async_call_with_retry`, so it is not converted into a relogin.
- Result: the integration can loop on decrypt errors instead of clearing auth (`_seq`, `_stok`, `_cookie`, and for outer-session firmwares the `_outer_*` fields) and re-authenticating.

Outer-session firmwares (documented for Deco S7 1.3.0 Build 20220609 Rel. 64814) use a legacy encrypted local-web session over HTTP. The same risk applies to any firmware that serves the LuCI API behind that outer session.

## 3. What to implement

### Unit test (preferred first step)

Add to `tests/test_api_transport_errors.py` (same style as existing tests in PR #598):

- Mock `_decrypt_data` to raise an exception (e.g. `ValueError` simulating bad padding).
- Authenticate the API first (set `_stok`, `_cookie`, `_seq`).
- Call `async_list_devices()` (or another `_async_*` method that goes through `_async_post` + `_decrypt_data`).
- Assert that:
  1. `clear_auth()` is called (or equivalently `_stok`, `_seq`, `_cookie` become None).
  2. A login follows (e.g. `async_login` is invoked, or a POST with `form=login` appears).
  3. The call eventually succeeds after relogin.

### Optional hardening

- In `_decrypt_data` or its caller, catch decrypt/padding failures and raise a dedicated exception (e.g. `InvalidSessionException`) that `_async_call_with_retry` treats like 401/403: clear auth, retry with login.
- For outer-session firmwares, also clear the `_outer_*` fields (`_clear_outer_auth()`), not only the LuCI session fields.

## 4. Real-world verification

On a Deco S7 (or X50 / XE75 if they use the same outer session):

1. Let the integration run normally.
2. Reboot one Deco from the Deco app or by power-cycling it.
3. Watch Home Assistant logs for decrypt/padding errors.
4. Confirm the integration self-recovers: session cleared, relogin, polling resumes, no manual intervention.
5. Compare with firmware that returns 401/403 on invalid session (already covered by existing tests).

## 5. Notes

- Tested devices include Deco X50 and Deco XE75 (user's own hardware: one X50 + one XE75).
- The S7 firmware is the only one explicitly documented as using the outer encrypted session; behavior on X50/XE75 should be confirmed.
- Related: user's earlier PRs #520 and #521 were closed as superseded; remaining items from #521 were proposed as follow-up small PRs but not yet submitted.
