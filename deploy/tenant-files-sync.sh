#!/usr/bin/env bash
#
# Nightly per-tenant file sync (sp-sal0ci).
#
#   tenant-files-sync.sh [instance]        (default: prod)
#
# Litestream replicates databases, not files. Each tenant's photos live in
# tenant-files/<database_id>/ and go to
# s3://<bucket>/mtgc-<inst>/tenant-files/<database_id>/.
#
# The walk is over the REGISTRY, keyed by database_id — never over the
# directory, and never by handle. A handle can be re-created for a different
# person; a database_id cannot, so a re-created handle has no route to a
# predecessor's images, in S3 or on disk.
#
# One tenant failing does not stop the walk and does not hide: every tenant is
# attempted, each is reported, and the exit status is the worst of them
# (pd-s5…: never silently do one tenant).
#
# No --delete: a file removed by its owner stays in the bucket for the
# retention window; purge, not sync, is what removes data.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/litestream-lib.sh
. "$SCRIPT_DIR/litestream-lib.sh"

INSTANCE="${1:-prod}"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
[ -f "${CONF_DIR}/${INSTANCE}.env" ] && { set -a; . "${CONF_DIR}/${INSTANCE}.env"; set +a; }

BUCKET="$(mtgc_ls_bucket)"
HOME_DIR="$(mtgc_ls_home "$INSTANCE")"
IDS="$(mtgc_ls_tenant_ids "$HOME_DIR/registry.sqlite")"

ENDPOINT_ARGS=()
[ -n "${MTGC_BACKUP_S3_ENDPOINT:-}" ] && ENDPOINT_ARGS=(--endpoint-url "${MTGC_BACKUP_S3_ENDPOINT}")

failed=0 synced=0
while IFS= read -r id; do
    [ -n "$id" ] || continue
    src="$HOME_DIR/tenant-files/$id"
    if [ ! -d "$src" ]; then
        echo "tenant-files-sync: $id has no tenant-files directory — nothing to sync"
        continue
    fi
    echo "tenant-files-sync: $id"
    if aws s3 sync "${ENDPOINT_ARGS[@]}" "$src/" \
            "s3://${BUCKET}/mtgc-${INSTANCE}/tenant-files/${id}/"; then
        synced=$((synced + 1))
    else
        echo "tenant-files-sync: FAILED for $id" >&2
        failed=$((failed + 1))
    fi
done <<< "$IDS"

echo "tenant-files-sync: ${synced} synced, ${failed} failed"
[ "$failed" -eq 0 ]
