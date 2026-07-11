---
name: ha-tplink-deco-release
description: Manage releases for the rjullien/ha-tplink-deco Home Assistant HACS fork — versioning (X.Y.Z.N), manifest/README updates, PR merge, GitHub release tag, and HACS verification. Use when the user asks to release, tag, publish, bump version, or ship a HACS update.
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
| CI workflow | `.github/workflows/tests.yaml` (pre-commit, HACS, hassfest) |
| Default branch | `main` |

## Versioning scheme (mandatory)

Format: **`X.Y.Z.N`** (4 parts)

| Part | Meaning | Example |
|------|---------|---------|
| `X.Y.Z` | Upstream base version this fork is aligned on | `3.9.1` |
| `N` | Fork revision on that base (0, 1, 2…) | `0` |

Examples:
- First fork release on upstream 3.9.1 → **`3.9.1.0`**
- Fork-only fix, same upstream base → **`3.9.1.1`**
- Upstream releases 3.10.0, fork aligns → **`3.10.0.0`**

**Rules:**
- `manifest.json` version = release version **without** `v` prefix (`3.9.1.0`)
- Git tag and GitHub release = **with** `v` prefix (`v3.9.1.0`)
- Tag name must match manifest version exactly (modulo the `v`)

Update README fork status block when upstream alignment changes:

```markdown
> **Fork status:** Aligned with upstream [amosyuen/ha-tplink-deco](https://github.com/amosyuen/ha-tplink-deco) **vX.Y.Z** (commit `abcdef1`, YYYY-MM-DD).
> **Versioning:** `X.Y.Z.N` — `X.Y.Z` = upstream base, `N` = fork revision.
```

## Pre-release checklist

Run through this list **before** creating the tag:

1. **Version bumped** in `custom_components/tplink_deco/manifest.json`
2. **Changelog entry** added at top of `README.md` under `### vX.Y.Z.N`
3. **Fork status** line updated if upstream alignment changed
4. **PR merged** into `main` (or changes committed on `main`)
5. **CI green** on the merge commit:
   ```bash
   gh pr checks <PR_NUMBER> --repo rjullien/ha-tplink-deco
   # or inspect the latest main workflow run
   ```
6. **Tag does not exist** yet:
   ```bash
   git fetch origin --tags
   git tag -l 'v<VERSION>'
   ```
7. **Local validation** (if Python available):
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

Edit:
- `custom_components/tplink_deco/manifest.json` → `"version": "X.Y.Z.N"`
- `README.md` → new changelog section + fork status if needed

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

```bash
VERSION="3.9.1.0"          # no v prefix
PREV_TAG="v3.14.1"         # previous release tag
TITLE="v${VERSION} — Short human-readable summary"

gh release create "v${VERSION}" \
  --repo rjullien/ha-tplink-deco \
  --title "${TITLE}" \
  --notes "## Highlights

One-line summary.

### Fixes
- ...

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
- Do **not** merge a full `upstream/main` blindly — cherry-pick functional fixes only (see upstream-align PRs)

## Upstream alignment releases

When syncing with amosyuen/ha-tplink-deco:

1. Fetch upstream: `git fetch upstream --tags`
2. Identify missing functional commits (not just dependabot)
3. Cherry-pick or port fixes preserving fork-only code (request lock, session churn, extended polling, security audit)
4. Set version `X.Y.Z.0` where `X.Y.Z` = upstream release (e.g. upstream v3.9.1 → fork `3.9.1.0`)
5. Document upstream commit hash in README fork status

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
