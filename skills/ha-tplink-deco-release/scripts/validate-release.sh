#!/usr/bin/env bash
# Validate that a release version is consistent across manifest, README, and git tags.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "Usage: $0 <VERSION>" >&2
  echo "Example: $0 3.9.1.0" >&2
  exit 1
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: Version must be 4-part semver (X.Y.Z.N), got: $VERSION" >&2
  exit 1
fi

TAG="v${VERSION}"
MANIFEST="${REPO_ROOT}/custom_components/tplink_deco/manifest.json"
README="${REPO_ROOT}/README.md"
ERRORS=0

fail() {
  echo "ERROR: $1" >&2
  ERRORS=$((ERRORS + 1))
}

warn() {
  echo "WARN: $1" >&2
}

ok() {
  echo "OK: $1"
}

# 1. manifest.json version
if [[ ! -f "$MANIFEST" ]]; then
  fail "manifest.json not found at $MANIFEST"
else
  MANIFEST_VERSION=$(grep -o '"version": "[^"]*"' "$MANIFEST" | head -1 | cut -d'"' -f4)
  if [[ "$MANIFEST_VERSION" != "$VERSION" ]]; then
    fail "manifest.json version is '$MANIFEST_VERSION', expected '$VERSION'"
  else
    ok "manifest.json version = $VERSION"
  fi
fi

# 2. README changelog section
if [[ ! -f "$README" ]]; then
  fail "README.md not found"
else
  if grep -q "### v${VERSION}" "$README"; then
    ok "README.md has changelog section ### v${VERSION}"
  else
    fail "README.md missing changelog section '### v${VERSION}'"
  fi

  # 2a. Fork status block
  if grep -q "> \*\*Fork status:\*\*" "$README"; then
    ok "README.md has fork status block"
  else
    fail "README.md missing fork status block (> **Fork status:**)"
  fi

  if grep -q "> \*\*Versioning:\*\*" "$README"; then
    ok "README.md documents versioning scheme"
  else
    fail "README.md missing versioning line (> **Versioning:**)"
  fi

  # 2b. Changelog has at least one bullet under the version heading
  BULLET_COUNT=$(sed -n "/^### v${VERSION}\$/,/^---\$/p" "$README" | grep -c '^- ' || true)
  if [[ "$BULLET_COUNT" -ge 1 ]]; then
    ok "README changelog v${VERSION} has ${BULLET_COUNT} bullet(s)"
  else
    fail "README changelog '### v${VERSION}' has no bullet points (- ...)"
  fi

  # 2c. New changelog is near the top (first version heading in changelog section)
  FIRST_VERSION_LINE=$(sed -n '/^## 📝 Changelog$/,/^## /p' "$README" | grep '^### v' | head -1)
  if [[ "$FIRST_VERSION_LINE" == "### v${VERSION}" ]]; then
    ok "README changelog v${VERSION} is the latest entry (first ### v)"
  else
    fail "README changelog v${VERSION} is not the first entry (found: ${FIRST_VERSION_LINE:-none})"
  fi

  # 2d. Separator after changelog entry (recommended)
  if sed -n "/^### v${VERSION}\$/,/^### v/p" "$README" | grep -q '^---$'; then
    ok "README changelog v${VERSION} followed by --- separator"
  else
    warn "README changelog v${VERSION} missing --- separator before previous entry"
  fi
fi

# 3. Tag must not already exist on origin
git fetch origin --tags --quiet 2>/dev/null || true
if git rev-parse "$TAG" >/dev/null 2>&1; then
  warn "Tag $TAG already exists locally"
  if git ls-remote --tags origin "refs/tags/${TAG}" | grep -q "$TAG"; then
    fail "Tag $TAG already exists on origin — bump version before releasing"
  fi
else
  ok "Tag $TAG does not exist yet (ready to create)"
fi

# 4. On main branch with clean tree (informational)
BRANCH=$(git branch --show-current)
if [[ "$BRANCH" != "main" ]]; then
  warn "Not on main branch (current: $BRANCH)"
fi
if [[ -n "$(git status --porcelain)" ]]; then
  warn "Working tree has uncommitted changes"
else
  ok "Working tree clean"
fi

# 5. Python syntax check
if command -v python3 >/dev/null 2>&1; then
  if python3 -m compileall custom_components/tplink_deco -q; then
    ok "Python compileall passed"
  else
    fail "Python compileall failed"
  fi
else
  warn "python3 not found — skipping compileall"
fi

echo ""
if [[ $ERRORS -gt 0 ]]; then
  echo "Validation FAILED ($ERRORS error(s))" >&2
  exit 1
fi

echo "Validation PASSED for version $VERSION (tag: $TAG)"
echo ""
echo "Next step:"
echo "  gh release create ${TAG} --repo rjullien/ha-tplink-deco \\"
echo "    --title \"v${VERSION} — <short description>\" \\"
echo "    --notes \"<release notes>\""
