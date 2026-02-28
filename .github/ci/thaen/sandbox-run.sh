#!/usr/bin/env bash
set -euo pipefail

# Runs a Claude plan or implement agent inside a Podman container.
#
# Usage: sandbox-run.sh <plan|implement> <issue_number> <repo> [base_branch]
# Env:   ANTHROPIC_API_KEY, GH_TOKEN (bot account: thaen-claude)
#
# Plan mode:  Claude explores the codebase and writes a plan to /out/plan-comment.md.
#             Post-run: post plan comment, advance label to ready_for_human_plan_review.
# Implement:  Claude implements the approved plan, pushes a branch, opens a PR.
#             Post-run: verify PR exists, advance label to ready_for_human_review.
#
# Host paths (macOS /opt ↔ VM /var/opt via virtiofs):
#   /opt/dd-ci-code/   — git clone + Linux .venv (overlay-mounted read-only)
#   /opt/dd-ci-data/   — MTGC_HOME: DB, AllPrintings.json, prices, certs
#   /opt/dd-ci-claude/  — Claude CLI (npm prefix, bind-mounted)

MODE="$1"
ISSUE_NUMBER="$2"
REPO="$3"
BASE_BRANCH="${4:-main}"

if [[ "$MODE" != "plan" && "$MODE" != "implement" ]]; then
    echo "Error: mode must be 'plan' or 'implement', got '$MODE'" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${MODE}-${ISSUE_NUMBER}-$(date +%Y%m%d-%H%M%S).log"

# --- Load bot token (thaen-claude) ---
# Local runs: always load from claude-bot.env (overrides any personal GH_TOKEN).
# CI runs: GH_TOKEN is set by the workflow from secrets.CLAUDE_BOT_TOKEN.
if [ -z "${GITHUB_ACTIONS:-}" ]; then
    BOT_ENV="$HOME/.config/mtgc/claude-bot.env"
    if [ -f "$BOT_ENV" ]; then
        export GH_TOKEN=$(grep '^GH_TOKEN=' "$BOT_ENV" | cut -d= -f2-)
    fi
fi
if [ -z "${GH_TOKEN:-}" ]; then
    echo "Error: GH_TOKEN not set and ~/.config/mtgc/claude-bot.env not found" >&2
    exit 1
fi

# --- Derive trigger label and workflow file from mode ---
if [ "$MODE" = "plan" ]; then
    TRIGGER_LABEL="ready_for_claude_plan"
    WORKFLOW_FILE="plan.yml"
else
    TRIGGER_LABEL="ready_for_claude_implement"
    WORKFLOW_FILE="implement.yml"
fi

# --- Local runs: run preflight first (CI already ran it as a separate step) ---
if [ -z "${GITHUB_ACTIONS:-}" ]; then
    AUTHOR=$(gh api "repos/${REPO}/issues/${ISSUE_NUMBER}" --jq '.user.login')
    echo "Local run — running preflight for issue #${ISSUE_NUMBER} (author: ${AUTHOR})"
    PREFLIGHT_OUT=$(bash "$SCRIPT_DIR/preflight.sh" "$ISSUE_NUMBER" "$REPO" "$AUTHOR" "" "$TRIGGER_LABEL" "$WORKFLOW_FILE")
    PREFLIGHT_RC=$?
    echo "$PREFLIGHT_OUT"
    if [ $PREFLIGHT_RC -ne 0 ]; then
        exit 1
    fi
    if echo "$PREFLIGHT_OUT" | grep -q "^SKIP:"; then
        exit 0
    fi
fi

# --- For implement mode, require "Make it so" from thaen ---
if [[ "$MODE" == "implement" ]]; then
    if ! gh api "repos/${REPO}/issues/${ISSUE_NUMBER}/comments" --jq '
        .[] | select(.user.login == "thaen") | .body
    ' | grep -q "Make it so"; then
        echo "Error: no 'Make it so' comment from thaen on issue #${ISSUE_NUMBER}. Aborting." >&2
        exit 1
    fi
    echo "Approval found. Proceeding with implementation."
fi

# --- Build the image ---
CONTAINERFILE="$REPO_DIR/.github/containers/thaen/ci-server.containerfile"
echo "Building dd-ci-server image..."
podman build -t dd-ci-server -f "$CONTAINERFILE" "$REPO_DIR"

# --- VM-side paths (macOS /opt maps to VM /var/opt via virtiofs) ---
VM_CODE="/var/opt/dd-ci-code"
VM_DATA="/var/opt/dd-ci-data"
VM_CLAUDE="/var/opt/dd-ci-claude"

# --- Temp dir for plan output (must be under /opt which maps to VM /var/opt) ---
CI_OUT="/opt/dd-ci-out/$$"
mkdir -p "$CI_OUT"
VM_CI_OUT="/var/opt/dd-ci-out/$$"
PLAN_FILE="$CI_OUT/plan-comment.md"

echo "Logging to $LOG_FILE"

# --- Name the container so we can force-kill it on interrupt ---
CONTAINER_NAME="dd-ci-${MODE}-${ISSUE_NUMBER}-$$"
cleanup() {
    echo "Caught signal — stopping container $CONTAINER_NAME"
    podman stop -t 2 "$CONTAINER_NAME" 2>/dev/null || true
    exit 130
}
trap cleanup INT TERM

podman run --rm \
    --name "$CONTAINER_NAME" \
    --memory=4g \
    -v "${VM_CODE}:/app:O" \
    -v "${VM_DATA}:/data:O" \
    -v "${VM_CLAUDE}:/opt/claude:ro" \
    -v "${VM_CI_OUT}:/out" \
    -e ANTHROPIC_API_KEY \
    -e GH_TOKEN \
    -e ISSUE_NUMBER="$ISSUE_NUMBER" \
    -e REPO_FULL_NAME="$REPO" \
    -e MODE="$MODE" \
    -e MTGC_HOME=/data \
    -e BASE_BRANCH="$BASE_BRANCH" \
    --entrypoint bash \
    dd-ci-server /app/.github/ci/thaen/entrypoint.sh 2>&1 | tee "$LOG_FILE"
CONTAINER_RC=${PIPESTATUS[0]}
echo "Container exited with code $CONTAINER_RC"

# --- Post plan comment + advance label ---
PLAN_TAG="<!-- thaen-claude-plan -->"

if [ "$MODE" = "plan" ] && [ "$CONTAINER_RC" -eq 0 ]; then
    if [ ! -s "$PLAN_FILE" ]; then
        echo "WARNING: container exited cleanly but no plan file at $PLAN_FILE" >&2
        exit 1
    fi

    echo "Plan file found: $(wc -c < "$PLAN_FILE") bytes"

    # Verify the plan file has the required tag
    if ! head -1 "$PLAN_FILE" | grep -qF "$PLAN_TAG"; then
        echo "WARNING: plan file missing required tag ($PLAN_TAG) on first line" >&2
        echo "First line: $(head -1 "$PLAN_FILE")"
        exit 1
    fi
    echo "Plan tag verified"

    # Delete existing plan comment (if re-planning)
    echo "Checking for existing plan comment..."
    EXISTING_COMMENT_ID=$(gh api "repos/${REPO}/issues/${ISSUE_NUMBER}/comments" \
        --jq ".[] | select(.body | startswith(\"${PLAN_TAG}\")) | .id" \
        | head -1)
    if [ -n "$EXISTING_COMMENT_ID" ]; then
        echo "Deleting existing plan comment $EXISTING_COMMENT_ID"
        gh api -X DELETE "repos/${REPO}/issues/${ISSUE_NUMBER}/comments/${EXISTING_COMMENT_ID}"
    else
        echo "No existing plan comment found"
    fi

    # Post new plan
    echo "Posting plan comment..."
    gh issue comment "$ISSUE_NUMBER" --repo "$REPO" --body-file "$PLAN_FILE"
    echo "Plan comment posted to issue #$ISSUE_NUMBER"

    # Advance label
    echo "Advancing label: ready_for_claude_plan → ready_for_human_plan_review"
    gh issue edit "$ISSUE_NUMBER" --repo "$REPO" \
        --remove-label ready_for_claude_plan \
        --add-label ready_for_human_plan_review
    echo "Labels updated"
fi

# --- Verify implementation + advance label ---
if [ "$MODE" = "implement" ] && [ "$CONTAINER_RC" -eq 0 ]; then
    BRANCH="claude/issue-${ISSUE_NUMBER}"

    # Verify the PR was created by Claude inside the container
    PR_URL=$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --json url --jq '.[0].url' 2>/dev/null || true)
    if [ -z "$PR_URL" ]; then
        echo "WARNING: container exited cleanly but no open PR found for branch $BRANCH" >&2
        exit 1
    fi
    echo "PR found: $PR_URL"

    # Advance label
    echo "Advancing label: ready_for_claude_implement → ready_for_human_review"
    gh issue edit "$ISSUE_NUMBER" --repo "$REPO" \
        --remove-label ready_for_claude_implement \
        --add-label ready_for_human_review
    echo "Labels updated"
fi

# --- Cleanup ---
rm -rf "$CI_OUT"
