#!/usr/bin/env bash
#
# The Litestream sidecar for one instance: render the config, then replicate
# (sp-sal0ci). Run by mtgc-litestream-<inst>.service; replicates until killed.
set -euo pipefail
INSTANCE="${1:-prod}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
# shellcheck source=deploy/litestream-lib.sh
. "$SCRIPT_DIR/litestream-lib.sh"
[ -f "${CONF_DIR}/${INSTANCE}.env" ] && { set -a; . "${CONF_DIR}/${INSTANCE}.env"; set +a; }

# 78 (EX_CONFIG) is in the unit's RestartPreventExitStatus: a missing binary does
# not heal by retrying, so it fails once and pages once, not every 30 seconds.
command -v litestream >/dev/null 2>&1 \
    || { echo "litestream-run.sh: litestream not found on PATH ($PATH)" >&2; exit 78; }

CONFIG="$(mktemp)"
trap 'rm -f "$CONFIG"' EXIT
bash "$SCRIPT_DIR/litestream-config.sh" "$INSTANCE" > "$CONFIG"
litestream replicate -config "$CONFIG"
