#!/usr/bin/env bash
set -euo pipefail

# --- Auth ---
# gh uses GH_TOKEN from the environment automatically; no login needed.
git config --global credential.helper \
    '!f() { echo "password=${GH_TOKEN}"; }; f'
git config --global user.name "claude-ci[bot]"
git config --global user.email "claude-ci[bot]@users.noreply.github.com"

REPO_URL="https://x-access-token:${GH_TOKEN}@github.com/${REPO_FULL_NAME}.git"

# --- Clone or update repo ---
if [ ! -d /workspace/.git ]; then
    git clone "$REPO_URL" /workspace
else
    git -C /workspace remote set-url origin "$REPO_URL"
fi

cd /workspace
git clean -fd
git checkout -- .
git fetch origin
git config core.hooksPath hooks/

# Use BASE_BRANCH if set, otherwise default to main
BASE="${BASE_BRANCH:-main}"
git checkout "$BASE"
git rebase "origin/$BASE"

# --- Install/update deps (fast no-op if unchanged) ---
uv sync --group dev

# --- Prepare writable DB copy for server/screenshots ---
# /data is mounted read-only; the server needs a writable DB.
# MTGC_DB is checked by get_db_path() before MTGC_HOME, so the server
# (and all CLI commands) find the writable copy automatically — no --db flag needed.
if [ -f /data/collection.sqlite ]; then
    cp /data/collection.sqlite /tmp/collection.sqlite
    chmod 644 /tmp/collection.sqlite
    export MTGC_DB=/tmp/collection.sqlite
fi

# For implement mode, create/checkout an issue branch
if [ "$MODE" = "implement" ]; then
    BRANCH="claude/issue-${ISSUE_NUMBER}"
    git checkout -B "$BRANCH"
fi

# --- Dispatch ---
PROMPT_FILE="/app/ci/prompts/${MODE}.md"
PROMPT=$(ISSUE_NUMBER="$ISSUE_NUMBER" REPO_FULL_NAME="$REPO_FULL_NAME" envsubst < "$PROMPT_FILE")

claude --dangerously-skip-permissions \
    -p "$PROMPT" \
    --max-turns 50 \
    --verbose \
    --output-format stream-json
