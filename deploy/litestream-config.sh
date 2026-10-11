#!/usr/bin/env bash
#
# Render the Litestream config for one instance to stdout (sp-sal0ci).
#
#   litestream-config.sh [instance]        (default: prod)
#
# Three replicated things, nothing per tenant:
#   - registry.sqlite       the control plane
#   - tenants/*.sqlite      directory mode: a tenant created later is picked up
#                           live, with no config edit and no restart
#   - collection.sqlite     today's single-tenant database, until it moves into
#                           tenants/. Replicated beside the tarball so the drill
#                           can pass on prod before anything else changes.
# shared.sqlite is the catalogue: rebuildable, not replicated.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/litestream-lib.sh
. "$SCRIPT_DIR/litestream-lib.sh"

INSTANCE="${1:-prod}"
HOME_DIR="$(mtgc_ls_home "$INSTANCE")"
# Directory mode needs the directory. Creating the empty one is the layout, not a
# fallback: tenants/ is where tenants live whether or not any exist yet.
mkdir -p "$HOME_DIR/tenants"

cat <<YAML
dbs:
  - path: ${HOME_DIR}/collection.sqlite
    replica:
      url: $(mtgc_ls_replica_url "$INSTANCE" collection)
  - path: ${HOME_DIR}/registry.sqlite
    replica:
      url: $(mtgc_ls_replica_url "$INSTANCE" registry)
  - dir: ${HOME_DIR}/tenants
    pattern: "*.sqlite"
    watch: true
    replica:
      url: $(mtgc_ls_replica_url "$INSTANCE" tenants)
YAML
