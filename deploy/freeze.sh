#!/usr/bin/env bash
#
# Deploy freeze: a marker a production cutover sets and deploy.sh honours.
#
# On 2026-10-14, 20 minutes into the multi-tenancy cutover (mtgc-prod stopped on
# purpose, a legacy-migrate container reading the volume), a merged batch PR ran
# deploy.sh prod, which rebuilt the image and RESTARTED mtgc-prod over the
# migration (sp-4vlkdc). Nothing in the pipeline knew a maintenance window was
# open. This is the thing that tells it.
#
# Usage:
#   freeze.sh set   <instance> --holder <who> --reason <why> --until <epoch|ISO8601>
#   freeze.sh clear <instance>
#   freeze.sh check <instance>   exit 1 + the marker's contents if frozen, else 0
#   freeze.sh alarm <instance>   exit 0 if no marker or still in window; if the
#                                stated end has passed, push an alert and exit 1
#
# The marker is ~/.config/mtgc/freeze-<instance> (override the directory with
# MTGC_FREEZE_DIR). Plain KEY=value lines, read with grep and never sourced.
#
# A marker past its end STILL blocks deploys: a freeze that lifts itself is a
# cutover that can be deployed over after all. What expiry changes is that
# `alarm` (the mtgc-freeze-check timer) says so, loudly, until a human clears it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FREEZE_DIR="${MTGC_FREEZE_DIR:-$HOME/.config/mtgc}"

usage() { sed -n '/^# Usage:/,/^# The marker/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

[ $# -ge 2 ] || usage
CMD="$1"; INSTANCE="$2"; shift 2
MARKER="$FREEZE_DIR/freeze-${INSTANCE}"

field() { grep -m1 "^$1=" "$MARKER" | cut -d= -f2-; }

case "$CMD" in
set)
    HOLDER="" REASON="" UNTIL=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --holder) HOLDER="${2:?--holder needs a value}"; shift 2 ;;
            --reason) REASON="${2:?--reason needs a value}"; shift 2 ;;
            --until)  UNTIL="${2:?--until needs a value}"; shift 2 ;;
            *) usage ;;
        esac
    done
    if [ -z "$HOLDER" ] || [ -z "$REASON" ] || [ -z "$UNTIL" ]; then
        echo "freeze.sh: set needs --holder, --reason and --until" >&2
        exit 2
    fi
    case "$UNTIL" in
        ''|*[!0-9]*) UNTIL_EPOCH="$(date -d "$UNTIL" +%s)" ;;
        *) UNTIL_EPOCH="$UNTIL" ;;
    esac
    if [ -e "$MARKER" ]; then
        echo "freeze.sh: $INSTANCE is already frozen:" >&2
        cat "$MARKER" >&2
        exit 1
    fi
    mkdir -p "$FREEZE_DIR"
    TMP="$(mktemp "$MARKER.XXXXXX")"
    {
        printf 'HOLDER=%s\n' "${HOLDER//$'\n'/ }"
        printf 'REASON=%s\n' "${REASON//$'\n'/ }"
        printf 'SET_AT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'UNTIL=%s\n' "$UNTIL_EPOCH"
        printf 'UNTIL_ISO=%s\n' "$(date -u -d "@$UNTIL_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"
    } > "$TMP"
    mv "$TMP" "$MARKER"
    echo "freeze.sh: $INSTANCE frozen until $(field UNTIL_ISO) by $HOLDER"
    ;;
clear)
    rm -f "$MARKER"
    echo "freeze.sh: $INSTANCE freeze cleared"
    ;;
check)
    [ -e "$MARKER" ] || exit 0
    {
        echo "DEPLOY FROZEN: $INSTANCE is held by a maintenance window; refusing to touch it."
        echo "Marker: $MARKER"
        cat "$MARKER"
        if [ "$(date +%s)" -gt "$(field UNTIL)" ]; then
            echo "NOTE: the stated end has passed. The holder must finish and run: freeze.sh clear $INSTANCE"
        else
            echo "To lift (holder only): bash deploy/freeze.sh clear $INSTANCE"
        fi
    } >&2
    exit 1
    ;;
alarm)
    [ -e "$MARKER" ] || exit 0
    NOW="$(date +%s)"
    UNTIL_EPOCH="$(field UNTIL)"
    [ "$NOW" -gt "$UNTIL_EPOCH" ] || exit 0
    MSG="Deploy freeze on $INSTANCE ran past its end ($(field UNTIL_ISO)); held by $(field HOLDER): $(field REASON). Deploys stay blocked until cleared: bash deploy/freeze.sh clear $INSTANCE"
    echo "$MSG" >&2
    bash "$SCRIPT_DIR/alert.sh" "MTGC freeze overdue ($INSTANCE)" "$MSG"
    exit 1
    ;;
*) usage ;;
esac
