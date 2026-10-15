#!/usr/bin/env bash
#
# Shared by the Litestream scripts (sp-sal0ci): where an instance's data lives,
# where its replicas live, and what a tenant id looks like.
#
# Sourced, not run. Callers have set -euo pipefail.

# shellcheck source=deploy/store-lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/store-lib.sh"

# litestream-install.sh puts the binary in ~/.local/bin, which the systemd user
# manager's PATH (Ubuntu's /etc/environment) does not name: the unit died with
# "litestream: command not found" on every start (sp-fgve20). Every script that
# runs litestream sources this, so it resolves the installed binary wherever it
# is started from, and a deploy's own exported PATH is not what makes it work.
export PATH="${MTGC_LITESTREAM_BIN_DIR:-$HOME/.local/bin}:$PATH"

# mtgc_ls_home <instance> — the directory holding registry.sqlite, tenants/ and
# tenant-files/ (the volume mount; /data inside the container). MTGC_LITESTREAM_HOME
# names it outright; only tests use that, production asks podman.
mtgc_ls_home() {
    local instance="$1" volume
    if [ -n "${MTGC_LITESTREAM_HOME:-}" ]; then
        printf '%s\n' "$MTGC_LITESTREAM_HOME"
        return 0
    fi
    volume="mtgc-${instance}-data"
    # The volume lives in the store the instance's unit records (de-3mo).
    mtgc_store_adopt_instance "$instance"
    mtgc_store_activate
    podman volume exists "$volume" \
        || { echo "ERROR: volume '$volume' not found." >&2; return 1; }
    podman volume inspect "$volume" --format '{{.Mountpoint}}'
}

# mtgc_ls_bucket — the backup bucket, or a hard error. No bucket, no replica.
mtgc_ls_bucket() {
    [ -n "${MTGC_BACKUP_S3_BUCKET:-}" ] \
        || { echo "ERROR: MTGC_BACKUP_S3_BUCKET is unset — there is nowhere to replicate to." >&2; return 1; }
    printf '%s\n' "$MTGC_BACKUP_S3_BUCKET"
}

# mtgc_ls_region — the bucket's region, or a hard error. litestream asks S3 for
# it when none is named, and the mtgc-backup role is (rightly) denied
# GetBucketLocation, so the unit died at start (sp-yplovy). No fallback, and the
# role is not widened.
mtgc_ls_region() {
    [ -n "${MTGC_BACKUP_S3_REGION:-}" ] \
        || { echo "ERROR: MTGC_BACKUP_S3_REGION is unset — litestream cannot look the bucket region up under the least-privilege backup role." >&2; return 1; }
    printf '%s\n' "$MTGC_BACKUP_S3_REGION"
}

# mtgc_ls_restore_url <instance> <kind> [suffix] — the replica URL for a CLI
# restore, which has no config to carry a region: it rides as a query parameter.
mtgc_ls_restore_url() {
    local url region
    url="$(mtgc_ls_replica_url "$1" "$2")${3:-}" || return 1
    region="$(mtgc_ls_region)" || return 1
    printf '%s?region=%s\n' "$url" "$region"
}

# mtgc_ls_replica_url <instance> <kind> — s3://bucket/mtgc-<inst>/litestream/<kind>.
# Kept apart from the tarball prefix's daily/ so backup-check.sh's listing of
# mtgc-<inst>/ is not skewed by replica segments.
mtgc_ls_replica_url() {
    local instance="$1" kind="$2" bucket
    bucket="$(mtgc_ls_bucket)" || return 1
    printf 's3://%s/mtgc-%s/litestream/%s\n' "$bucket" "$instance" "$kind"
}

# mtgc_ls_valid_id <id> — an uppercase Crockford ULID, 26 characters. The id is
# a path component and an S3 key component: anything else is refused rather than
# normalised, because a lowercased or truncated id names a different tenant.
mtgc_ls_valid_id() {
    [[ "$1" =~ ^[0-9A-HJKMNP-TV-Z]{26}$ ]]
}

# mtgc_ls_tenant_ids <registry.sqlite> — every database_id the registry holds,
# detached ones included (a detached tenant's data is still inside its
# retention window), one per line, in rowid order. A malformed id is an error.
mtgc_ls_tenant_ids() {
    local registry="$1" id
    [ -f "$registry" ] || { echo "ERROR: registry not found at $registry" >&2; return 1; }
    local ids
    ids="$(python3 -I - "$registry" <<'PY'
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
for (db_id,) in con.execute("SELECT database_id FROM user ORDER BY rowid"):
    print(db_id)
PY
)" || return 1
    while IFS= read -r id; do
        [ -n "$id" ] || continue
        mtgc_ls_valid_id "$id" \
            || { echo "ERROR: registry holds a malformed database_id: '$id'" >&2; return 1; }
        printf '%s\n' "$id"
    done <<< "$ids"
}
