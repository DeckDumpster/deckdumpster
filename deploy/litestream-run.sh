#!/usr/bin/env bash
#
# The Litestream sidecar for one instance: render the config, then replicate
# (sp-sal0ci). Run by mtgc-litestream-<inst>.service; replicates until killed.
set -euo pipefail
INSTANCE="${1:-prod}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
[ -f "${CONF_DIR}/${INSTANCE}.env" ] && { set -a; . "${CONF_DIR}/${INSTANCE}.env"; set +a; }

CONFIG="$(mktemp)"
trap 'rm -f "$CONFIG"' EXIT
bash "$SCRIPT_DIR/litestream-config.sh" "$INSTANCE" > "$CONFIG"
litestream replicate -config "$CONFIG"
