# Agent instructions

This repository is a **fork** of [amosyuen/ha-tplink-deco](https://github.com/amosyuen/ha-tplink-deco) with fork-specific improvements (session lock, extended polling, security audit).

## Skills (repo root)

Agent skills live in [`skills/`](skills/) — tool-agnostic, version-controlled runbooks.

| Skill                                                            | When to use                                           |
| ---------------------------------------------------------------- | ----------------------------------------------------- |
| [ha-tplink-deco-release](skills/ha-tplink-deco-release/SKILL.md) | Release, tag, publish, bump version, ship HACS update |

**Before any release task:** read and follow [skills/ha-tplink-deco-release/SKILL.md](skills/ha-tplink-deco-release/SKILL.md) completely.

Validator script:

```bash
bash skills/ha-tplink-deco-release/scripts/validate-release.sh <VERSION>
```

## Versioning

Fork uses **4-part** versions: `X.Y.Z.N` (`X.Y.Z` = upstream base, `N` = fork revision). See the release skill for details.

## Documentation on release

Every release must update docs **in the same commit** as the version bump. The release skill defines:

- `README.md` changelog (top of `## 📝 Changelog`, mandatory)
- Fork status block (when upstream alignment changes)
- GitHub release notes (mirror README changelog)
- `hacs.json` / HA badge (only if min HA version changes)

Run `bash skills/ha-tplink-deco-release/scripts/validate-release.sh <VERSION>` before tagging.

## Key paths

- Integration: `custom_components/tplink_deco/`
- Tests: `tests/` (pytest + coverage, see `requirements-dev.txt`)
- Version: `custom_components/tplink_deco/manifest.json`
- Changelog: `README.md` → `## 📝 Changelog`
- HACS config: `hacs.json`

## Cursor Cloud specific instructions

Python 3.12 HA custom integration. The startup update script provisions a repo-root `.venv` and installs deps (constrained `homeassistant` + `pycryptodome`, then `requirements.txt` and `requirements-dev.txt`). Always use the venv (`.venv/bin/...`).

- **Stale proxy env vars (important).** `~/.bashrc` exports `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` pointing at `localhost:1054`/`1055` (Tailscale userspace ports), but no proxy runs there — so any command that reaches the network (`pip`, `hass` alert fetch) fails with "Cannot connect to proxy" unless you bypass them. Direct egress works. Prefix network commands with `env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy ...` (or `unset` them in the shell first). `apt` is unaffected.
- **Run HA (dev):** `export PYTHONPATH="$PWD" && .venv/bin/hass --config "$PWD/config" --debug` → serves at http://localhost:8123. `PYTHONPATH` must be the **repo root**, not `custom_components/`; HA does `import custom_components` and iterates its `__path__`, so only the repo root makes the integration discoverable ("We found a custom integration tplink_deco" in the log). Note `.devcontainer/develop.sh` sets `PYTHONPATH=$PWD/custom_components`, which does NOT trigger discovery under `hass` — use the repo root instead (or copy/symlink the integration into `config/custom_components/`, which is gitignored).
- **Lint (pre-commit gate):** `PATH="$PWD/.venv/bin:$PATH" .venv/bin/pre-commit run --all-files`. The `black`/`flake8`/`isort` hooks use `language: system`, so the venv bin MUST be on `PATH` or they fail with "Executable not found". `ruff` is installed but is NOT part of the pre-commit/CI lint gate.
- **Tests:** `.venv/bin/pytest` (config in `setup.cfg`; coverage gate `fail_under = 75`).
- **Harmless startup errors:** `default_config` optional components (`cloud`, `go2rtc`, `dhcp`, `conversation`, `mobile_app`, camera turbojpeg) fail to set up because their extra deps/binaries aren't installed, and `homeassistant_alerts`/`aiodns` network calls error out (no live proxy). None of these affect developing or testing the `tplink_deco` integration — core `http`/`frontend`/`config`/`websocket_api`/`config_flow` load fine.
