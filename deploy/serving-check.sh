#!/usr/bin/env bash
#
# Is the instance answering on the listener its mode serves? (sp-8lil3y)
#
# The body of mtgc-serving-check-<instance>.service. Exits 0 when alive, 1 when
# the container is down or the listener does not answer; the unit fails on 1.
# Resolution lives in origin-lib.sh — this carries no port of its own.
#
# Usage: serving-check.sh <instance>
set -uo pipefail

INSTANCE="${1:?usage: serving-check.sh <instance>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=origin-lib.sh
source "$SCRIPT_DIR/origin-lib.sh"

if mtgc_origin_alive "$INSTANCE"; then
    echo "serving-check: ${INSTANCE} OK (${ORIGIN_MODE}, ${ORIGIN_URL}${ORIGIN_PROBE})"
else
    echo "serving-check: ${INSTANCE} FAILED" >&2
    exit 1
fi
