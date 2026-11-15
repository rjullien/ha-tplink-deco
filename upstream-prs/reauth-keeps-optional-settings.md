# Reauthentication keeps name and syslog settings

Title: Preserve name and syslog settings during reauthentication

## Summary

A successful reauthentication resets the optional name and syslog settings of
the config entry.

`async_step_reauth_confirm()` calls `_ensure_user_input_optionals()` on the
submitted form, which only contains the username and password. The client and
Deco prefixes/postfixes and the syslog host are therefore set to `""` in
`user_input`, then `data.update(user_input)` overwrites the stored values:

- Deco tracker names lose the default `Deco` postfix (`DEFAULT_DECO_POSTFIX`),
  and custom client/Deco prefixes and postfixes are lost;
- with syslog forwarding enabled, `syslog_enabled` stays `True` while
  `syslog_host` becomes empty.

The call has been there since the prefix/postfix options were added (#171);
`syslog_host` joined the list in v3.15.0. We found it by reading the code while
syncing our fork, not from a user report.

## Change

- Remove the `_ensure_user_input_optionals()` call from
  `async_step_reauth_confirm()`. The submitted credentials are merged into the
  stored entry data, which already contains these keys (set by
  `async_step_user()` and by the entry migration). The user and options flows
  are unchanged.

## Testing

`tests/test_config_flow.py::test_reauth_keeps_name_and_syslog_settings`
stores custom prefixes/postfixes and an enabled syslog destination, submits a
new password through `async_step_reauth_confirm()`, and checks that both the
credential test and the saved entry receive the stored data with only the
password replaced.

Against upstream `main` before the fix:

```text
FAILED tests/test_config_flow.py::test_reauth_keeps_name_and_syslog_settings
```

With the fix, full suite:

```text
223 passed, 1 warning in 4.29s
```

Pre-commit passed locally (black, flake8, isort, prettier and the
pre-commit-hooks checks).

## Diff stat

`git diff --stat upstream/main...fix/reauth-keeps-optional-settings`:

```text
 custom_components/tplink_deco/config_flow.py |  1 -
 tests/test_config_flow.py                    | 36 ++++++++++++++++++++++++++++
 2 files changed, 36 insertions(+), 1 deletion(-)
```
