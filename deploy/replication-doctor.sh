#!/usr/bin/env bash
#
# Is a multi-tenant instance's replication actually running? (sp-5sq7wk)
#
#   replication-doctor.sh [instance]       (default: prod)
#   replication-doctor.sh --enable [instance]
#
# Installed timers are not running timers: mtgc-litestream, mtgc-litestream-check
# and mtgc-tenant-files sat installed-but-disabled for the first day of
# multi-tenant production, and every deploy reported green. Without --enable
# this only checks, names every unit that is not running, and exits 1. With
# --enable it enables and starts them first, then checks — deploy.sh does that.
#
# An instance is multi-tenant when MTGC_MULTITENANT=1 is in its env files or a
# registry.sqlite exists in its data volume. Anything else has no tenant
# databases to replicate and passes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/litestream-lib.sh
. "$SCRIPT_DIR/litestream-lib.sh"

ENABLE=false
if [ "${1:-}" = "--enable" ]; then ENABLE=true; shift; fi
INSTANCE="${1:-prod}"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

multitenant=false
if grep -qs '^MTGC_MULTITENANT=1' "${CONF_DIR}/${INSTANCE}.env" "${CONF_DIR}/${INSTANCE}/access.env"; then
    multitenant=true
else
    home_dir="$(mtgc_ls_home "$INSTANCE")"
    [ -f "$home_dir/registry.sqlite" ] && multitenant=true
fi
if [ "$multitenant" = false ]; then
    echo "replication-doctor: ${INSTANCE} is not multi-tenant — nothing to replicate"
    exit 0
fi

TIMERS=(mtgc-litestream mtgc-litestream-check mtgc-tenant-files)
if [ "$ENABLE" = true ]; then
    for u in "${TIMERS[@]}"; do
        systemctl --user enable --now "${u}-${INSTANCE}.timer"
    done
    # The sidecar is kept up by its timer on a 5 minute cadence; do not wait.
    systemctl --user start "mtgc-litestream-${INSTANCE}.service" || true
fi

bad=()
command -v litestream >/dev/null 2>&1 || bad+=("litestream binary (not on PATH)")
for u in "${TIMERS[@]}"; do
    t="${u}-${INSTANCE}.timer"
    systemctl --user is-enabled --quiet "$t" 2>/dev/null || bad+=("$t (not enabled)")
    systemctl --user is-active --quiet "$t" 2>/dev/null || bad+=("$t (not active)")
done
s="mtgc-litestream-${INSTANCE}.service"
systemctl --user is-active --quiet "$s" 2>/dev/null || bad+=("$s (not running)")

if [ "${#bad[@]}" -gt 0 ]; then
    echo "replication-doctor: FAIL — ${INSTANCE} is multi-tenant but replication is not running:" >&2
    printf '  - %s\n' "${bad[@]}" >&2
    exit 1
fi
echo "replication-doctor: OK — ${INSTANCE} replication units are enabled and running"
