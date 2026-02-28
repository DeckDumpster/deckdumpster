#!/bin/bash
# Auto-approve safe Bash commands via PreToolUse hook.
# Workaround for settings.json allow rules not preventing permission prompts:
#   https://github.com/anthropics/claude-code/issues/18160
#   https://github.com/anthropics/claude-code/issues/18846
#   https://github.com/anthropics/claude-code/issues/20449
#
# Deny rules are checked first, then allow, then falls through to
# the normal permission prompt for anything unrecognized.

set -e

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

[ -z "$COMMAND" ] && exit 0

# Extract first real command word, skipping env var assignments (VAR=val)
first_word=$(echo "$COMMAND" | awk '{for(i=1;i<=NF;i++){if(index($i,"=")==0){print $i;exit}}}')

decide() {
  local decision="$1" reason="$2"
  jq -n --arg d "$decision" --arg r "$reason" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: $d,
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

# --- DENY (checked first) ---

if [ "$first_word" = "rm" ]; then
  if echo "$COMMAND" | grep -qE '^rm\s+(-rf|-fr)\s'; then
    decide deny "Blocked: rm -rf"
  fi
fi

if [ "$first_word" = "sudo" ]; then
  decide deny "Blocked: sudo"
fi

if [ "$first_word" = "git" ]; then
  if echo "$COMMAND" | grep -qE '^git\s+push\s+.*--force'; then
    decide deny "Blocked: git push --force"
  fi
  if echo "$COMMAND" | grep -qE '^git\s+reset\s+--hard'; then
    decide deny "Blocked: git reset --hard"
  fi
  if echo "$COMMAND" | grep -qE '^git\s+clean\s+-f'; then
    decide deny "Blocked: git clean -f"
  fi
fi

# --- ALLOW ---

allowed_commands=(
  ls pwd cat head tail wc find grep echo which date mkdir
  git uv python3 curl podman gh
  shot-scraper
)

for allowed in "${allowed_commands[@]}"; do
  if [ "$first_word" = "$allowed" ]; then
    decide allow "Auto-approved: $first_word"
  fi
done

# systemctl/journalctl --user only
if [ "$first_word" = "systemctl" ] || [ "$first_word" = "journalctl" ]; then
  if echo "$COMMAND" | grep -q -- '--user'; then
    decide allow "Auto-approved: $first_word --user"
  fi
fi

# Fall through: normal permission prompt
exit 0
