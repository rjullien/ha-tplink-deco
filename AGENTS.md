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

This is a Home Assistant custom integration (single Python package, no
frontend build). Dependencies live in a `.venv` at the repo root, created by
the startup update script. Activate it first: `source .venv/bin/activate`
(or call tools directly via `.venv/bin/<tool>`).

- **Lint:** `pre-commit run --all-files` (black, flake8, isort, prettier). Also
  described in `CONTRIBUTING.md`. The first run downloads the prettier hook env.
- **Test:** `pytest` (config in `setup.cfg`; 55 tests, coverage gate 75%).
- **Run the app:** `.devcontainer/develop.sh` starts Home Assistant on port
  8123 using the `config/` dir. It only sets `PYTHONPATH`, which is NOT enough
  for HA to discover the custom integration.
- **Gotcha — integration discovery:** HA only loads custom integrations from
  `config/custom_components/`. Before starting HA, symlink it once (the whole
  `config/` dir except `configuration.yaml` is git-ignored, so this is not
  committed):
  `mkdir -p config/custom_components && ln -sfn ../../custom_components/tplink_deco config/custom_components/tplink_deco`
  Then run HA and restart it after adding the symlink so the config flow appears.
- **Gotcha — offline VM:** Harmless `aiodns Channel.getaddrinfo()` TypeErrors
  and `homeassistant_alerts` connection errors appear at startup because the VM
  has no outbound DNS; they do not block HA from initializing or the integration
  from working.
- **No hardware needed to exercise the integration end to end:** the config
  flow / API talk to a real Deco over an RSA+AES handshake. A tiny mock router
  that implements just that handshake (login, `device_list`, `client_list`,
  `performance`) is enough to complete the config flow and create
  `device_tracker`/sensor entities against `http://127.0.0.1:8080` with
  "Verify SSL" unchecked. See `tests/fixtures/` for the expected payload shapes.
