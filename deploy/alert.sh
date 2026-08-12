#!/usr/bin/env bash
#
# Push a notification via Pushover — the notification sink shared by
# deploy/backup-check.sh (a stale backup on a live box) and
# deploy/mtgc-alert@.service (any unit's journal tail on failure).
#
# Mirrors pokedumpster:deploy/alert.sh, including its central decision: asked to
# alert and unable to alert is a FAILURE (exit 1), not a no-op. Nothing calls
# this speculatively — every caller has already concluded something is wrong, so
# an unconfigured channel means that conclusion reached nobody. Exiting non-zero
# makes the calling unit fail, which is the only remaining way to see it.
#
# Reads PUSHOVER_TOKEN / PUSHOVER_USER from the environment; the host-wide file
# is ~/.config/mtgc/alerts.env. No runtime deps beyond curl.
#
# Usage:
#   alert.sh "<title>" "<message>"     # message as an argument
#   some_cmd | alert.sh "<title>"      # message on stdin (e.g. a journal tail)
set -euo pipefail

# Production never sets this; tests point it at a local sink to prove the push
# actually leaves the script.
PUSHOVER_API_URL="${PUSHOVER_API_URL:-https://api.pushover.net/1/messages.json}"

TITLE="${1:-MTGC alert}"
if [ "$#" -ge 2 ]; then
    MSG="$2"
else
    MSG="$(cat)"
fi

# CHANGE_ME is the scaffolded placeholder. A placeholder that reached curl would
# fail the request anyway, just later and less legibly.
if [ -z "${PUSHOVER_TOKEN:-}" ] || [ -z "${PUSHOVER_USER:-}" ] \
   || [ "${PUSHOVER_TOKEN}" = CHANGE_ME ] || [ "${PUSHOVER_USER}" = CHANGE_ME ]; then
    echo "alert.sh: FAILED — PUSHOVER_TOKEN/USER unset or still CHANGE_ME; this alert reached nobody." >&2
    echo "  Dropped alert: ${TITLE}" >&2
    echo "  Fix: fill ~/.config/mtgc/alerts.env (see deploy/README.md)." >&2
    exit 1
fi

# Pushover caps messages at 1024 chars; trim to stay well under.
MSG="$(printf '%s' "$MSG" | tail -c 900)"

curl -fsS -m 15 \
    --form-string "token=${PUSHOVER_TOKEN}" \
    --form-string "user=${PUSHOVER_USER}" \
    --form-string "title=${TITLE}" \
    --form-string "message=${MSG}" \
    --form-string "priority=${PUSHOVER_PRIORITY:-0}" \
    "$PUSHOVER_API_URL" >/dev/null
