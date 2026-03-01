#!/usr/bin/env bash
# Generate ephemeral session context for Claude Code SessionStart hook.
# Stdout: context text injected into the session.
# Stderr: timing info for investigation.
#
# Usage:
#   bash scripts/session-context.sh              # normal run
#   bash scripts/session-context.sh --timing     # print per-section timing to stderr

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

TIMING=false
[[ "${1:-}" == "--timing" ]] && TIMING=true

_t() { if $TIMING; then gdate +%s%N 2>/dev/null || date +%s000000000; fi; }
_elapsed() {
  if $TIMING; then
    local ms=$(( ($2 - $1) / 1000000 ))
    echo "  [$3: ${ms}ms]" >&2
  fi
}

TOTAL_START=$(_t)

# --- Current state ---
S=$(_t)
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "detached")
DIRTY_COUNT=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
STAGED_COUNT=$(git diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ')
UNSTAGED_COUNT=$(git diff --name-only 2>/dev/null | wc -l | tr -d ' ')
UNTRACKED_COUNT=$(git ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ')

echo "# Session Context (generated)"
echo ""
echo "## Working state"
echo "- Branch: \`$BRANCH\`"
if [[ "$DIRTY_COUNT" -eq 0 ]]; then
  echo "- Tree: clean"
else
  echo "- Tree: ${STAGED_COUNT} staged, ${UNSTAGED_COUNT} modified, ${UNTRACKED_COUNT} untracked"
  # Show what's dirty
  git status --porcelain 2>/dev/null | head -15 | while IFS= read -r line; do
    echo "  - \`$line\`"
  done
  if [[ "$DIRTY_COUNT" -gt 15 ]]; then
    echo "  - ... and $((DIRTY_COUNT - 15)) more"
  fi
fi
E=$(_t)
_elapsed "$S" "$E" "working-state"

# --- Recent commits on this branch ---
S=$(_t)
echo ""
echo "## Recent commits"

# Find divergence point from main (or just show last 10)
MERGE_BASE=$(git merge-base HEAD main 2>/dev/null || echo "")
if [[ -n "$MERGE_BASE" && "$BRANCH" != "main" ]]; then
  BRANCH_COMMITS=$(git rev-list --count "$MERGE_BASE"..HEAD 2>/dev/null || echo "0")
  if [[ "$BRANCH_COMMITS" -gt 0 ]]; then
    echo "Branch has $BRANCH_COMMITS commit(s) ahead of main:"
    git log --oneline "$MERGE_BASE"..HEAD 2>/dev/null | head -10 | while IFS= read -r line; do
      echo "- $line"
    done
  else
    echo "Branch is at main. Recent commits:"
    git log --oneline -5 2>/dev/null | while IFS= read -r line; do
      echo "- $line"
    done
  fi
else
  git log --oneline -5 2>/dev/null | while IFS= read -r line; do
    echo "- $line"
  done
fi
E=$(_t)
_elapsed "$S" "$E" "recent-commits"

# --- Hot files (most frequently changed in last 20 commits) ---
S=$(_t)
echo ""
echo "## Hot files (most changed in last 20 commits)"
git log --pretty=format: --name-only -20 2>/dev/null \
  | grep -v '^$' \
  | sort \
  | uniq -c \
  | sort -rn \
  | head -8 \
  | while read -r count name; do
    echo "- \`$name\` ($count commits)"
  done
E=$(_t)
_elapsed "$S" "$E" "hot-files"

# --- Test fixture staleness ---
S=$(_t)
FIXTURE="tests/fixtures/test-data.sqlite"
SCHEMA_PY="mtg_collector/db/schema.py"
if [[ -f "$FIXTURE" && -f "$SCHEMA_PY" ]]; then
  WARNINGS=""
  # Extract SCHEMA_VERSION from code
  CODE_VERSION=$(grep -m1 '^SCHEMA_VERSION' "$SCHEMA_PY" | grep -o '[0-9]\+')
  # Extract max version from fixture
  FIXTURE_VERSION=$(sqlite3 "$FIXTURE" "SELECT MAX(version) FROM schema_version;" 2>/dev/null || echo "?")

  if [[ "$FIXTURE_VERSION" != "$CODE_VERSION" ]]; then
    WARNINGS="${WARNINGS}\n- Schema mismatch: fixture is v${FIXTURE_VERSION}, code is v${CODE_VERSION}. Run \`uv run python scripts/build_test_fixture.py\`"
  fi

  # Check if build script is newer than fixture
  if [[ "scripts/build_test_fixture.py" -nt "$FIXTURE" ]]; then
    WARNINGS="${WARNINGS}\n- \`build_test_fixture.py\` is newer than fixture. Rebuild may be needed."
  fi

  if [[ -n "$WARNINGS" ]]; then
    echo ""
    echo "## Test fixture warnings"
    echo -e "$WARNINGS"
  fi
fi
E=$(_t)
_elapsed "$S" "$E" "fixture-check"

# --- Stashes ---
S=$(_t)
STASH_COUNT=$(git stash list 2>/dev/null | wc -l | tr -d ' ')
if [[ "$STASH_COUNT" -gt 0 ]]; then
  echo ""
  echo "## Stashes ($STASH_COUNT)"
  git stash list 2>/dev/null | head -3 | while IFS= read -r line; do
    echo "- $line"
  done
fi
E=$(_t)
_elapsed "$S" "$E" "stashes"

TOTAL_END=$(_t)
_elapsed "$TOTAL_START" "$TOTAL_END" "TOTAL"
