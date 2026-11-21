# Options flow re-tests changed credentials after a validation error

Title: Re-test changed credentials after an options validation error

## Summary

The options flow can save new credentials without testing them.

`async_step_init()` only calls `_async_test_credentials()` when the submitted
host, username, password or SSL setting differs from `self.data`. But
`self.data` is updated with the submitted values before validation and keeps
them when validation fails. If a submit changes the password and also has an
invalid interval, the form comes back with the interval error. On the corrected
submit the new password already matches `self.data`, so
`connection_settings_changed` is `False` and the entry is saved without a
credential test.

The comparison was added in #563. We found it by reading the code while syncing
our fork, not from a user report.

## Change

- Compare the connection settings with the stored entry
  (`self.config_entry.data`) instead of the flow's working copy, so changed
  connection settings are tested on every submit until they are saved.

## Testing

`tests/test_config_flow.py::test_options_retests_changed_credentials_after_invalid_interval`
submits a new password with an invalid device list interval, then the same
password with a valid interval, and checks that the second submit runs the
credential test, shows its error and does not update the entry.

Against upstream `main` before the fix:

```text
FAILED tests/test_config_flow.py::test_options_retests_changed_credentials_after_invalid_interval
1 failed, 53 passed, 1 warning in 2.01s
```

With the fix, full suite:

```text
224 passed, 1 warning in 3.49s
```

Pre-commit passed locally (check for added large files, check yaml, fix end of
files, trim trailing whitespace, black, flake8, ISort, prettier).

## Diff stat

`git diff --stat upstream/main...fix/options-retest-changed-credentials`:

```text
 custom_components/tplink_deco/config_flow.py |  5 +++--
 tests/test_config_flow.py                    | 24 ++++++++++++++++++++++++
 2 files changed, 27 insertions(+), 2 deletions(-)
```
