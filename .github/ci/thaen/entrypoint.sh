#!/usr/bin/env bash
set -euo pipefail

# Container-internal entrypoint for CI planning/implementation.
#
# Expected env: GH_TOKEN, ISSUE_NUMBER, REPO_FULL_NAME,
#               MODE (plan|implement), BASE_BRANCH (default: main)
#
# Expected mounts:
#   /app        — repo code (overlay on /opt/dd-ci-code snapshot)
#   /data       — MTGC data (overlay on /opt/dd-ci-data snapshot)
#   /opt/claude — Claude CLI (bind-mount from /opt/dd-ci-claude)

# --- Claude CLI ---
export PATH="/opt/claude/bin:$PATH"

# --- Git auth (runs as root; overlay files are root-owned) ---
git config --global --add safe.directory /app
git config --global credential.helper \
    '!f() { echo "password=${GH_TOKEN}"; }; f'
git config --global user.name "thaen-claude"
git config --global user.email "thaen-claude@users.noreply.github.com"

REPO_URL="https://x-access-token:${GH_TOKEN}@github.com/${REPO_FULL_NAME}.git"

# --- Update repo to latest (overlay starts from pre-populated snapshot) ---
cd /app
git remote set-url origin "$REPO_URL"
git fetch origin

BASE="${BASE_BRANCH:-main}"
git checkout "$BASE"
git reset --hard "origin/$BASE"

# --- Install/update deps (overlay venv has --no-dev, plan needs dev deps) ---
uv sync --group dev

# --- Writable DB copy ---
# /data is overlay-mounted; the server needs a writable DB.
# MTGC_DB is checked by get_db_path() before MTGC_HOME.
if [ -f /data/collection.sqlite ]; then
    cp /data/collection.sqlite /tmp/collection.sqlite
    chmod 644 /tmp/collection.sqlite
    export MTGC_DB=/tmp/collection.sqlite
fi

# --- For implement mode, create/checkout an issue branch ---
if [ "$MODE" = "implement" ]; then
    BRANCH="claude/issue-${ISSUE_NUMBER}"
    git checkout -B "$BRANCH"
    # Overlay upper layer is root-owned; give ci write access to source files.
    chown -R ci:ci /app
fi

# --- Build prompt from template ---
PROMPT_FILE="/app/.github/ci/thaen/prompts/${MODE}.md"
PROMPT=$(ISSUE_NUMBER="$ISSUE_NUMBER" REPO_FULL_NAME="$REPO_FULL_NAME" envsubst < "$PROMPT_FILE")

# --- Run Claude as non-root (refuses --dangerously-skip-permissions as root) ---
# Preserve MTGC_DB so the agent uses the writable DB copy.
runuser -u ci -- env MTGC_DB="${MTGC_DB:-}" MTGC_HOME="${MTGC_HOME:-}" \
    claude --dangerously-skip-permissions \
    -p "$PROMPT" \
    --max-turns 50 \
    --verbose \
    --output-format stream-json
