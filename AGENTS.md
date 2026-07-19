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

This is a Home Assistant custom integration (Python 3.12). The update script provisions a `.venv` at the repo root with `requirements.txt` (pins `homeassistant==2025.1.0`), `requirements-dev.txt` (pytest), and the integration runtime dep `pycryptodome`. Activate it with `. .venv/bin/activate` before running any tool below.

- **Test:** `pytest` from repo root (config lives in `setup.cfg`; enforces ≥75% coverage on `api`/`config_flow`/`coordinator`).
- **Lint:** `pre-commit run --all-files` (black, flake8, isort, prettier). `pre-commit install` is not required for one-off runs.
- **Run HA dev instance:** `.devcontainer/develop.sh` starts Home Assistant at `http://localhost:8123` using the `config/` dir. Run it in a long-lived (tmux) session; first boot takes ~15s and downloads the frontend.
- **Integration discovery gotcha:** HA loads custom integrations from `config/custom_components/`, but the integration source lives in `custom_components/` at the repo root. Create the symlink `ln -sfn ../custom_components config/custom_components` (gitignored — `config/*` is ignored except `configuration.yaml`) so HA discovers `tplink_deco`. `develop.sh`'s `PYTHONPATH` tweak alone is not sufficient for discovery.
- **No hardware in cloud:** There is no reachable TP-Link Deco router, so completing the config flow returns `Unable to connect to host.` — this is expected and still proves the config flow + API path run end-to-end. Full device-tracker behavior requires a real Deco and is covered by the mocked `pytest` suite.
- **Harmless startup noise:** logs show a Python 3.12 deprecation warning and a `homeassistant_alerts`/`aiodns` `getaddrinfo` TypeError (external network fetch); neither affects the integration.
