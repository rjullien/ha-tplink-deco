---
name: ha-tplink-deco-release
description: Manage releases for the rjullien/ha-tplink-deco Home Assistant HACS fork — versioning (X.Y.Z.N), documentation updates (README changelog, fork status, GitHub release notes), manifest updates, PR merge, GitHub release tag, and HACS verification. Use when the user asks to release, tag, publish, bump version, or ship a HACS update.
---

# ha-tplink-deco-release

Runbook for publishing a new version of **rjullien/ha-tplink-deco** (HACS custom integration).

## When to use

- User asks to **release**, **tag**, **publish**, **ship**, or **bump version**
- After merging a feature/fix PR that should reach HACS users
- When aligning on a new upstream base version

## Repository facts

| Item | Value |
|------|-------|
| GitHub repo | `rjullien/ha-tplink-deco` |
| HACS type | Custom integration (`hacs.json` at repo root) |
| Version file | `custom_components/tplink_deco/manifest.json` → `"version"` |
| Changelog | `README.md` → section `## 📝 Changelog` |
| Agent entrypoint | `AGENTS.md` → links to this skill |
| HACS config | `hacs.json` → min HA version (`homeassistant` key) |
| CI workflow | `.github/workflows/tests.yaml` (pre-commit, HACS, hassfest, **pytest**) |
| Default branch | `main` |

## Versioning scheme (mandatory)

Format: **`X.Y.Z.N`** (4 parts) — **aligned on upstream version numbers**

| Part | Meaning | Example |
|------|---------|---------|
| `X.Y.Z` | Upstream base version this fork is aligned on | `3.9.1` |
| `N` | Fork revision on that base (0, 1, 2…) | `1` |

Examples:
- First fork release on upstream 3.9.1 → **`3.9.1.0`**
- Fork-only fix, same upstream base → **`3.9.1.1`**
- Upstream releases 3.10.0, fork aligns → **`3.10.0.0`**

**Rules:**
- `manifest.json` version = release version **without** `v` prefix (`3.9.1.1`)
- Git tag and GitHub release = **with** `v` prefix (`v3.9.1.1`)

**HACS caveat (legacy fork users on v3.14.x):** AwesomeVersion treats `3.9.1.x` < `3.14.1`. HACS will **not** auto-offer the update. Document in README that users must **Redownload / Reinstall** from `rjullien/ha-tplink-deco`. This is intentional — upstream alignment of version numbers takes priority.

Update README fork status block when upstream alignment changes:

```markdown
> **Fork status:** Aligned with upstream [amosyuen/ha-tplink-deco](https://github.com/amosyuen/ha-tplink-deco) **vX.Y.Z** (commit `abcdef1`, YYYY-MM-DD).
> **Versioning:** `X.Y.Z.N` — `X.Y.Z` = upstream base, `N` = fork revision.
```

## Documentation updates (mandatory)

**Never release without updating docs in the same PR/commit as the version bump.** HACS has `render_readme: true` — users read `README.md` before updating.

### What to update, by release type

| File | Every release | Upstream align | Feature/fix only |
|------|---------------|----------------|------------------|
| `custom_components/tplink_deco/manifest.json` | ✅ version | ✅ | ✅ |
| `README.md` → changelog `### vX.Y.Z.N` | ✅ | ✅ | ✅ |
| `README.md` → fork status block | — | ✅ commit + date | — |
| GitHub release notes | ✅ | ✅ | ✅ |
| `README.md` → HA badge (`2026.x+`) | — | if min HA changed | if min HA changed |
| `hacs.json` → `homeassistant` | — | if min HA changed | if min HA changed |
| `AGENTS.md` | — | if paths/process change | — |
| `skills/ha-tplink-deco-release/SKILL.md` | — | if process changes | — |
| `translations/*.json` | — | if UI strings changed | if UI strings changed |

### README changelog rules

1. **Insert new section at the top** of the changelog (right after the fork status block), never at the bottom.
2. **Format:**
   ```markdown
   ### vX.Y.Z.N

   - Short bullet: what changed and why (link upstream PR if cherry-picked, e.g. #539)
   - Another bullet if needed
   - Mention fork improvements preserved when syncing upstream

   ---
   ```
3. **Bullets:** one change per line, past tense or imperative, include issue/PR numbers when relevant.
4. **Fork-only release** (`N` > 0, same upstream base): no fork status change needed.
5. **Upstream align** (`N` = 0 on new base): update fork status with upstream tag, commit hash, date.
6. **Do not delete** older changelog entries — this fork keeps full history (unlike upstream which removed old changelog).

### README changelog template

```markdown
### v3.9.1.1

- Fix: describe the user-visible fix
- Keep fork improvements: session lock, extended polling, security audit

---
```

### Sync README ↔ GitHub release notes

The GitHub release body must **mirror** the README changelog (same facts, can be slightly expanded):

| README changelog | GitHub release |
|------------------|----------------|
| `### v3.9.1.1` bullets | `## Highlights` + `### Fixes` / `### Features` sections |
| Fork status context | Optional one-liner in Highlights |
| Compare link | `**Full Changelog:** https://github.com/rjullien/ha-tplink-deco/compare/vPREV...vNEW` |

**Workflow:** write README changelog first, then copy/adapt to `gh release create --notes`.

### HA compatibility docs

When a fix targets a specific HA version (e.g. HA 2026.7 / aiohttp 3.14):

1. Mention it explicitly in the changelog bullet.
2. Update README badge if this becomes the new minimum:
   ```markdown
   [![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.7%2B-blue?style=for-the-badge)](...)
   ```
3. Update `hacs.json` `"homeassistant"` to match (keep in sync with badge).
4. Do **not** bump min HA version for fixes that are backward-compatible.

### Doc update step in release workflow

Include doc updates **in the same commit** as `manifest.json` version bump:

```bash
# Files to touch before opening PR:
custom_components/tplink_deco/manifest.json   # version
README.md                                    # changelog + fork status if needed
# After merge, separately:
# GitHub release notes (derived from README changelog)
```

### Doc validation

The validator checks manifest, changelog presence, fork status block, and changelog structure:

```bash
bash skills/ha-tplink-deco-release/scripts/validate-release.sh <VERSION>
```

Fix all `ERROR` lines before releasing. Review `WARN` lines consciously.

## Pre-release checklist

Run through this list **before** creating the tag:

1. **Version bumped** in `custom_components/tplink_deco/manifest.json`
2. **README changelog** added at top under `### vX.Y.Z.N` (with `---` separator, at least one bullet)
3. **Fork status** block updated if upstream alignment changed (commit hash + date)
4. **HA badge / hacs.json** updated if minimum HA version changed
5. **PR merged** into `main` (or changes committed on `main`)
6. **CI green** on the merge commit:
   ```bash
   gh pr checks <PR_NUMBER> --repo rjullien/ha-tplink-deco
   # or inspect the latest main workflow run
   ```
7. **Tag does not exist** yet:
   ```bash
   git fetch origin --tags
   git tag -l 'v<VERSION>'
   ```
8. **Tests pass** (pytest + coverage ≥ 45 % on core modules):
   ```bash
   pip install --constraint=requirements.txt homeassistant pycryptodome
   pip install -r requirements-dev.txt
   pytest
   ```
9. **Local validation** (if Python available):
   ```bash
   python3 -m compileall custom_components/tplink_deco -q
   pre-commit run --all-files   # optional but recommended
   ```

Run the bundled validator:

```bash
bash skills/ha-tplink-deco-release/scripts/validate-release.sh <VERSION>
# Example: bash skills/ha-tplink-deco-release/scripts/validate-release.sh 3.9.1.0
```

## Release workflow (step by step)

### 1. Prepare version on a branch (if not already done)

```bash
git checkout main
git pull origin main
git checkout -b cursor/<descriptive-name>-8019
```

Edit (same commit):
- `custom_components/tplink_deco/manifest.json` → `"version": "X.Y.Z.N"`
- `README.md` → new changelog section at top + fork status if upstream align
- `hacs.json` / README HA badge → only if min HA version changed

Commit, push, open PR, wait for CI.

### 2. Merge the PR

```bash
# If PR is still a draft:
gh pr ready <PR_NUMBER> --repo rjullien/ha-tplink-deco

# Squash merge (preferred — keeps main history clean):
gh pr merge <PR_NUMBER> --repo rjullien/ha-tplink-deco \
  --squash \
  --subject "feat: short summary (#<PR_NUMBER>)" \
  --body "Optional extended merge body."

git checkout main
git pull origin main
```

Verify merge commit is on `main` and CI passed.

### 3. Determine previous tag for changelog compare link

```bash
gh release list --repo rjullien/ha-tplink-deco --limit 5
# Pick the previous published tag (skip Draft entries)
```

### 4. Create GitHub release (HACS picks this up)

Build release notes from the README changelog written in step 1:

```bash
VERSION="3.9.1.0"          # no v prefix
PREV_TAG="v3.14.1"         # previous release tag
TITLE="v${VERSION} — Short human-readable summary"

gh release create "v${VERSION}" \
  --repo rjullien/ha-tplink-deco \
  --title "${TITLE}" \
  --notes "## Highlights

One-line summary (from README changelog).

### Fixes
- (copy/adapt bullets from README ### v${VERSION})

### Features
- ...

### CI / deps
- ...

**Full Changelog:** https://github.com/rjullien/ha-tplink-deco/compare/${PREV_TAG}...v${VERSION}"
```

**Release rules:**
- **Never** publish as `draft` (HACS needs a real release)
- **Never** use `prerelease` unless explicitly requested
- Title format: `vX.Y.Z.N — Short description` (matches historical releases)
- Notes: structured sections (Fixes / Features / CI) + compare link

### 5. Post-release verification

```bash
# Confirm release is live
gh release view "v${VERSION}" --repo rjullien/ha-tplink-deco

# Confirm manifest on tag matches
git show "v${VERSION}:custom_components/tplink_deco/manifest.json" | grep version
```

Tell the user how to update in HA:
1. HACS → Integrations → TP-Link Deco → **Update** / **Redownload**
2. Restart Home Assistant or reload the integration

## What NOT to do

- Do **not** copy upstream `manifest.json` version blindly (upstream uses 3-part semver; fork uses 4-part)
- Do **not** delete or overwrite upstream tags (`v3.9.1` from amosyuen fetch may exist locally — fork tag is `v3.9.1.0`)
- Do **not** release from a branch other than `main` without user approval
- Do **not** skip README changelog — HACS has `render_readme: true`
- Do **not** write GitHub release notes that contradict README changelog
- Do **not** add changelog entry at the bottom of README — always at the top
- HACS custom repo must be **`rjullien/ha-tplink-deco`** (not `amosyuen/ha-tplink-deco`)
- Do **not** merge a full `upstream/main` blindly — cherry-pick functional fixes only (see upstream-align PRs)

## Upstream alignment releases

When syncing with amosyuen/ha-tplink-deco:

1. Fetch upstream: `git fetch upstream --tags`
2. Identify missing functional commits (not just dependabot)
3. Cherry-pick or port fixes preserving fork-only code (request lock, session churn, extended polling, security audit)
4. Set version `X.Y.Z.0` where `X.Y.Z` = upstream release (e.g. upstream v3.9.1 → fork `3.9.1.0`)
5. Document upstream commit hash in README fork status
6. Write changelog bullets distinguishing upstream picks vs fork-only code preserved

## Example (v3.9.1.0 — reference release)

- **PR:** #9 merged via squash to `main`
- **Version:** `3.9.1.0` (upstream 3.9.1 + fork revision 0)
- **Title:** `v3.9.1.0 — Upstream align + HA 2026.7 fix`
- **URL:** https://github.com/rjullien/ha-tplink-deco/releases/tag/v3.9.1.0
- **Compare:** `v3.14.1...v3.9.1.0`

## Quick command reference

```bash
# Full happy path after PR is green
gh pr ready <N> --repo rjullien/ha-tplink-deco
gh pr merge <N> --repo rjullien/ha-tplink-deco --squash --subject "feat: ... (#<N>)"
git checkout main && git pull origin main
bash skills/ha-tplink-deco-release/scripts/validate-release.sh 3.9.1.1
gh release create v3.9.1.1 --repo rjullien/ha-tplink-deco --title "v3.9.1.1 — ..." --notes "..."
```
