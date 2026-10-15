#!/usr/bin/env bash
#
# Arm, disarm or inspect the lakehouse timer chain (lakehouse 14, K8).
#
#   chain.sh arm|disarm|status <instance>
#
# The chain is land -> derive -> prices -> ship -> value, one link per unit, all
# at 08:00 UTC, each After= the previous. The links only mean something
# together: a ship with no prices behind it values yesterday's catalogue, and a
# derive with no land behind it re-derives the same night. So `arm` is
# all-or-nothing and REFUSES a chain that is not whole -- a unit missing, a link
# not ordered after its predecessor, a link off the 08:00 clock, a retired timer
# still on the host, or the lake config / master key absent -- and enables
# nothing in that case. Installing units never arms them (units-lib.sh).
#
# Exit: 0 ok / armed; 1 refused or the chain is half armed; 2 usage.
set -euo pipefail

ACTION="${1:-}"
INSTANCE="${2:-}"
[ -n "$INSTANCE" ] && case "$ACTION" in arm|disarm|status) ;; *) ACTION="" ;; esac
[ -n "$ACTION" ] || { echo "usage: chain.sh arm|disarm|status <instance>" >&2; exit 2; }

CHAIN=(mtgc-land mtgc-derive mtgc-prices mtgc-ship mtgc-value)
RETIRED=(mtgc-catalog-refresh mtgc-sealed-catalog mtgc-edhrec)
UNIT_DIR="$HOME/.config/systemd/user"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"

problems=()
problem() { problems+=("$1"); }

check_whole() {
    local i prefix prev svc tmr
    for i in "${!CHAIN[@]}"; do
        prefix="${CHAIN[$i]}"
        svc="$UNIT_DIR/${prefix}-${INSTANCE}.service"
        tmr="$UNIT_DIR/${prefix}-${INSTANCE}.timer"
        [ -f "$svc" ] || { problem "${prefix}-${INSTANCE}.service is not installed (deploy.sh installs it)"; continue; }
        [ -f "$tmr" ] || { problem "${prefix}-${INSTANCE}.timer is not installed"; continue; }
        grep -q '^OnCalendar=\*-\*-\* 08:00:00 UTC$' "$tmr" \
            || problem "${prefix}-${INSTANCE}.timer is not on the 08:00 UTC chain clock"
        if [ "$i" -gt 0 ]; then
            prev="${CHAIN[$((i - 1))]}"
            grep -qE "^After=.*(^|[ ])${prev}-${INSTANCE}\.service( |$)" "$svc" \
                || problem "${prefix}-${INSTANCE}.service is not After= ${prev}-${INSTANCE}.service"
        fi
    done
    for prefix in "${RETIRED[@]}"; do
        if [ -e "$UNIT_DIR/${prefix}-${INSTANCE}.timer" ]; then
            problem "retired ${prefix}-${INSTANCE}.timer is still on the host (re-run deploy.sh)"
        fi
    done
    if systemctl --user is-enabled "mtgc-prices-${INSTANCE}.timer" >/dev/null 2>&1 \
        && ! grep -q 'lakehouse chain' "$UNIT_DIR/mtgc-prices-${INSTANCE}.service" 2>/dev/null; then
        problem "mtgc-prices-${INSTANCE} is still the old 06:00 unit (re-run deploy.sh)"
    fi
}

check_ready() {
    local env="$CONF_DIR/${INSTANCE}/lake.env" key="$CONF_DIR/${INSTANCE}/tenant-master.key" mode
    grep -q '^MTGC_LAKE_S3_BUCKET=.\+' "$env" 2>/dev/null || problem "MTGC_LAKE_S3_BUCKET is not set in $env"
    grep -q '^MTGC_LAKE_TENANT_URI=.\+' "$env" 2>/dev/null || problem "MTGC_LAKE_TENANT_URI is not set in $env"
    if [ -f "$key" ]; then
        mode="$(stat -c %a "$key")"
        [ "$mode" = 600 ] || problem "$key is mode $mode, not 600"
    else
        problem "the tenant master key $key is missing (deploy/LAKE-KEYS.md)"
    fi
}

enabled_count() {
    local n=0 prefix
    for prefix in "${CHAIN[@]}"; do
        systemctl --user is-enabled "${prefix}-${INSTANCE}.timer" >/dev/null 2>&1 && n=$((n + 1))
    done
    echo "$n"
}

timers=()
for prefix in "${CHAIN[@]}"; do timers+=("${prefix}-${INSTANCE}.timer"); done

case "$ACTION" in
    arm)
        check_whole
        check_ready
        if [ "${#problems[@]}" -gt 0 ]; then
            echo "chain: REFUSING to arm ${INSTANCE}; nothing enabled:" >&2
            printf '  - %s\n' "${problems[@]}" >&2
            exit 1
        fi
        systemctl --user enable --now "${timers[@]}"
        echo "chain: armed ${INSTANCE}: ${CHAIN[*]} at 08:00 UTC"
        ;;
    disarm)
        systemctl --user disable --now "${timers[@]}" || true
        echo "chain: disarmed ${INSTANCE}"
        ;;
    status)
        check_whole
        n="$(enabled_count)"
        echo "chain: ${n}/${#CHAIN[@]} timers enabled for ${INSTANCE}"
        if [ "${#problems[@]}" -gt 0 ]; then
            printf '  - %s\n' "${problems[@]}"
        fi
        if [ "$n" -ne 0 ] && [ "$n" -ne "${#CHAIN[@]}" ]; then
            echo "chain: HALF ARMED -- a part of the chain is silent" >&2
            exit 1
        fi
        [ "${#problems[@]}" -eq 0 ] || { [ "$n" -eq 0 ] || exit 1; }
        ;;
esac
