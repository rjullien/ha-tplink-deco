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

This is a Home Assistant custom integration (Python 3.12). The startup update script
creates a `.venv` and installs `requirements.txt`, `requirements-dev.txt`, and the
integration runtime dep `pycryptodome`. Activate it before any command: `source .venv/bin/activate`.

- Lint: `pre-commit run --all-files` (black, flake8, isort, prettier). The prettier hook
  auto-downloads its own Node env on first run.
- Test: `pytest` (config in `setup.cfg` already sets `pythonpath=.`, `testpaths=tests`,
  and coverage `fail_under=75`). ~55 tests, no network/router needed (API is mocked).
- Run the app (standalone HA): `hass --config config --debug`, serving on `http://localhost:8123`.
  See `.devcontainer/develop.sh` for the reference command.

Non-obvious gotchas:
- HA discovers custom integrations **only** from `config/custom_components/`. The
  `PYTHONPATH` trick in `develop.sh` alone does **not** make the integration appear in the
  UI. Before running `hass`, create the symlink (idempotent):
  `mkdir -p config/custom_components && ln -sfn ../../custom_components/tplink_deco config/custom_components/tplink_deco`.
  The whole `config/` dir (except `configuration.yaml`) is gitignored, so this symlink and
  HA state are ephemeral — recreate the symlink on a fresh checkout.
- First `hass` boot performs onboarding via the UI (create owner account) before the
  "Add Integration" flow is usable.
- The integration is `local_polling` and needs a real Deco router to fully configure. With
  no router reachable, the config flow correctly renders and returns "Unable to connect to
  host." on submit — that error path is the expected end-to-end demo without hardware.
- Harmless startup noise in logs: an `aiodns`/`pycares` `Channel.getaddrinfo()` TypeError
  from HA trying to reach external cloud/analytics endpoints. It does not affect the
  integration or local HA startup.
