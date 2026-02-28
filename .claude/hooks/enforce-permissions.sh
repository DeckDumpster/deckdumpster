#!/bin/bash
# Auto-approve safe Bash commands via PreToolUse hook.
# Workaround for settings.json allow rules not preventing permission prompts:
#   https://github.com/anthropics/claude-code/issues/18160
#   https://github.com/anthropics/claude-code/issues/18846
#   https://github.com/anthropics/claude-code/issues/20449
#
# Only auto-approves known-good commands. Everything else falls through
# to Claude's normal permission prompt (including deny decisions).

set -e

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

[ -z "$COMMAND" ] && exit 0

# Extract first real command word, skipping env var assignments (VAR=val)
first_word=$(echo "$COMMAND" | awk '{for(i=1;i<=NF;i++){if(index($i,"=")==0){print $i;exit}}}')

approve() {
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

allowed_commands=(
  ls pwd cat head tail wc find grep echo which date mkdir
  git uv python3 curl podman gh
  shot-scraper
)

for allowed in "${allowed_commands[@]}"; do
  if [ "$first_word" = "$allowed" ]; then
    approve "Auto-approved: $first_word"
  fi
done

# sqlite3: read-only queries only (no write keywords)
if [ "$first_word" = "sqlite3" ]; then
  if ! echo "$COMMAND" | grep -iqE '\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|VACUUM|REINDEX)\b'; then
    approve "Auto-approved: sqlite3 read-only"
  fi
fi

# systemctl/journalctl only with --user
if [ "$first_word" = "systemctl" ] || [ "$first_word" = "journalctl" ]; then
  if echo "$COMMAND" | grep -q -- '--user'; then
    approve "Auto-approved: $first_word --user"
  fi
fi

# Fall through: normal permission prompt
exit 0
