#!/usr/bin/env bash
set -euo pipefail

# Pre-container sanity checks for plan/implement workflows.
# Runs BEFORE the expensive Claude container to gate it cheaply.
#
# Usage: preflight.sh <issue_number> <repo> <author> [label] [trigger_label] [workflow_file]
# Env:   GH_TOKEN
#
# Arguments:
#   label          — event trigger label (github.event.label.name), fast-path reject
#   trigger_label  — required label the issue must have (default: ready_for_claude_plan)
#   workflow_file  — workflow filename for rate limiting (default: plan.yml)
#
# Exit 0 = skip (nothing to do — wrong label, closed, missing trigger label)
# Exit 1 = error (rate limit, unknown author)

ISSUE_NUMBER="$1"
REPO="$2"
AUTHOR="$3"
LABEL="${4:-}"
TRIGGER_LABEL="${5:-ready_for_claude_plan}"
WORKFLOW_FILE="${6:-plan.yml}"

ALLOWED_AUTHORS="thaen rgantt"
SKIP_LABELS="wontfix question duplicate invalid no-claude"
MAX_CONCURRENT_RUNS=3

# --- 0. Trigger label fast-path (no API call) ---
# If called from the workflow with a label arg, reject early if it's
# not the plan trigger. Saves an API call on every unrelated label event.
if [ -n "$LABEL" ] && [ "$LABEL" != "$TRIGGER_LABEL" ]; then
    echo "SKIP: label '$LABEL' is not '$TRIGGER_LABEL'"
    exit 0
fi

# --- 1. Author allowlist (no API call) ---
if ! echo "$ALLOWED_AUTHORS" | grep -qw "$AUTHOR"; then
    echo "SKIP: author '$AUTHOR' not in allowlist"
    exit 0
fi

# --- 2-5. Single gh call for issue state, body, labels ---
ISSUE_JSON=$(gh issue view "$ISSUE_NUMBER" --repo "$REPO" --json state,body,labels)

# 2. Issue state — must be OPEN
STATE=$(echo "$ISSUE_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")
if [ "$STATE" != "OPEN" ]; then
    echo "SKIP: issue #$ISSUE_NUMBER is $STATE"
    exit 0
fi

# 3. Body length — at least 20 chars
BODY_LEN=$(echo "$ISSUE_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('body','') or ''))")
if [ "$BODY_LEN" -lt 20 ]; then
    echo "SKIP: issue body too short ($BODY_LEN chars, need ≥20)"
    exit 0
fi

# 4. Required label — issue must have the trigger label
ISSUE_LABELS=$(echo "$ISSUE_JSON" | python3 -c "
import sys, json
labels = json.load(sys.stdin).get('labels', [])
print(' '.join(l['name'] for l in labels))
")
if ! echo "$ISSUE_LABELS" | grep -qw "$TRIGGER_LABEL"; then
    echo "SKIP: issue #$ISSUE_NUMBER does not have '$TRIGGER_LABEL' label"
    exit 0
fi

# 5. Skip labels
for label in $SKIP_LABELS; do
    if echo "$ISSUE_LABELS" | grep -qw "$label"; then
        echo "SKIP: issue has '$label' label"
        exit 0
    fi
done

# --- 6. Rate limit — max concurrent workflow runs ---
# Workflow may not exist yet (pre-merge) — treat 404 as 0 running.
RUNNING=$(gh run list --repo "$REPO" --workflow "$WORKFLOW_FILE" --status in_progress --json databaseId --jq 'length' 2>/dev/null || echo 0)
if [ "$RUNNING" -ge "$MAX_CONCURRENT_RUNS" ]; then
    echo "ERROR: $RUNNING ${WORKFLOW_FILE} workflows already running (max $MAX_CONCURRENT_RUNS)" >&2
    exit 1
fi

echo "Preflight passed for issue #$ISSUE_NUMBER"
