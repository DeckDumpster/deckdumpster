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

# Resolved before the heredoc: a failure inside $( ) in a heredoc does not abort.
URL_COLLECTION="$(mtgc_ls_replica_url "$INSTANCE" collection)"
URL_REGISTRY="$(mtgc_ls_replica_url "$INSTANCE" registry)"
URL_TENANTS="$(mtgc_ls_replica_url "$INSTANCE" tenants)"
REGION="$(mtgc_ls_region)"

cat <<YAML
dbs:
  - path: ${HOME_DIR}/collection.sqlite
    replica:
      url: ${URL_COLLECTION}
      region: ${REGION}
  - path: ${HOME_DIR}/registry.sqlite
    replica:
      url: ${URL_REGISTRY}
      region: ${REGION}
  - dir: ${HOME_DIR}/tenants
    pattern: "*.sqlite"
    watch: true
    replica:
      url: ${URL_TENANTS}
      region: ${REGION}
YAML
