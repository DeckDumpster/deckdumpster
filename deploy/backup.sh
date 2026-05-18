#!/usr/bin/env bash
#
# Back up an MTGC instance (database + images).
# Runs on the host, outside the container. No sudo required.
#
# Usage:
#   set -a && . ~/.config/mtgc/prod.env && set +a && bash deploy/backup.sh [instance]
#
#   The env file must be sourced with `set -a` (export all) so that
#   MTGC_BACKUP_S3_BUCKET and AWS_PROFILE are visible to the script.
#   Instance defaults to "prod" if omitted.
#
# What gets backed up:
#   - collection.sqlite  (online snapshot via sqlite3.backup())
#   - source_images/     (original uploaded photos)
#   - ingest_images/     (processed ingestion images)
#
# Backup directory (default ~/mtgc-backups):
#   Override with MTGC_BACKUP_DIR env var.
#
# Retention (after S3 upload succeeds, when MTGC_BACKUP_S3_BUCKET is set):
#   daily/   — last 2  (override with MTGC_KEEP_DAILY)
#   weekly/  — last 0  (override with MTGC_KEEP_WEEKLY)
#   monthly/ — last 0  (override with MTGC_KEEP_MONTHLY)
# Retention (local-only, when S3 is unset or upload fails):
#   daily/   — last 7
#   weekly/  — last 8 (~2 months)
#   monthly/ — last 12 (~1 year)
#
# S3 off-site sync (optional):
#   Set MTGC_BACKUP_S3_BUCKET to enable. Requires `aws` CLI configured.
#   Skipped silently if unset (local-only mode works out of the box).
#
#   Setup:
#     1. Create an IAM role with S3 access and a user that can assume it
#     2. aws configure                      # set base credentials for the user
#     3. Add a profile to ~/.aws/config:
#        [profile mtgc-backup]
#        role_arn = arn:aws:iam::ACCOUNT_ID:role/mtgc-backup-role
#        source_profile = default
#     4. aws s3 mb s3://your-bucket-name    # create bucket
#     5. Add to ~/.config/mtgc/<instance>.env:
#        MTGC_BACKUP_S3_BUCKET=your-bucket-name
#        AWS_PROFILE=mtgc-backup
#
set -euo pipefail

INSTANCE="${1:-prod}"
BACKUP_DIR="${MTGC_BACKUP_DIR:-$HOME/mtgc-backups}"
INSTANCE_DIR="${BACKUP_DIR}/${INSTANCE}"
DAILY_DIR="${INSTANCE_DIR}/daily"
WEEKLY_DIR="${INSTANCE_DIR}/weekly"
MONTHLY_DIR="${INSTANCE_DIR}/monthly"
STAGING_DIR="${INSTANCE_DIR}/staging"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
TARBALL_NAME="mtgc-${INSTANCE}-${TIMESTAMP}.tar.gz"

echo "==> MTGC backup"
echo "    Instance:  $INSTANCE"
echo "    Backup to: $INSTANCE_DIR"

# --- Ensure directories exist ---

mkdir -p "$DAILY_DIR" "$WEEKLY_DIR" "$MONTHLY_DIR"

# --- Discover the data volume mount on the host ---
#
# We snapshot host-side rather than via `podman exec` + `podman cp` so we
# don't need ~2× the DB size of free space inside the container's writable
# layer (a recurring source of silent disk-full failures). WAL mode on
# collection.sqlite makes a concurrent host-side sqlite3.backup() safe.

VOLUME_NAME="mtgc-${INSTANCE}-data"
if ! podman volume exists "$VOLUME_NAME" 2>/dev/null; then
    echo "ERROR: Volume '$VOLUME_NAME' not found."
    exit 1
fi
VOLUME_MOUNT="$(podman volume inspect "$VOLUME_NAME" --format '{{.Mountpoint}}')"
SRC_DB="${VOLUME_MOUNT}/collection.sqlite"
if [ ! -f "$SRC_DB" ]; then
    echo "ERROR: Database not found at $SRC_DB"
    exit 1
fi

# --- Pre-flight disk-space check ---
#
# Need room for: (a) the host-side sqlite snapshot (~DB size), and (b) the
# compressed tarball (~half of DB size in practice). Bail loudly rather than
# half-succeed and leave stale staging behind.

DB_BYTES=$(stat -c%s "$SRC_DB")
# Peak usage during backup ≈ snapshot copy + compressed tarball.
# Compressed tarball runs ~30% of DB size for this dataset (mostly IDs/numbers).
# Budget 1.4× DB + 200 MB headroom for images and gzip overhead.
NEEDED_BYTES=$((DB_BYTES + (DB_BYTES * 2 / 5) + 200 * 1024 * 1024))
AVAIL_BYTES=$(df --output=avail -B1 "$BACKUP_DIR" | tail -1)
if [ "$AVAIL_BYTES" -lt "$NEEDED_BYTES" ]; then
    AVAIL_MB=$((AVAIL_BYTES / 1024 / 1024))
    NEEDED_MB=$((NEEDED_BYTES / 1024 / 1024))
    echo "ERROR: only ${AVAIL_MB} MB free at $BACKUP_DIR, need ~${NEEDED_MB} MB."
    echo "       Free up space (e.g. 'podman image prune -af', prune old backups) and retry."
    exit 1
fi

# --- Create staging area ---

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
trap 'rm -rf "$STAGING_DIR"' EXIT

# --- Snapshot SQLite database (host-side) ---

echo "==> Creating SQLite snapshot from $SRC_DB ..."
python3 - "$SRC_DB" "$STAGING_DIR/collection.sqlite" <<'PY'
import sys, sqlite3
src_path, dst_path = sys.argv[1], sys.argv[2]
src = sqlite3.connect(src_path, timeout=60)
dst = sqlite3.connect(dst_path)
src.backup(dst)
dst.close()
src.close()
PY

# --- Copy images directly from the volume mount ---

for IMG_DIR in source_images ingest_images; do
    echo "==> Copying ${IMG_DIR}..."
    if [ -d "${VOLUME_MOUNT}/${IMG_DIR}" ]; then
        cp -a "${VOLUME_MOUNT}/${IMG_DIR}" "$STAGING_DIR/${IMG_DIR}"
    else
        echo "    (no ${IMG_DIR} directory — skipping)"
        mkdir -p "$STAGING_DIR/${IMG_DIR}"
    fi
done

# --- Create tarball ---

echo "==> Creating tarball: $TARBALL_NAME"
tar czf "$DAILY_DIR/$TARBALL_NAME" -C "$STAGING_DIR" \
    collection.sqlite source_images ingest_images

TARBALL_SIZE=$(du -h "$DAILY_DIR/$TARBALL_NAME" | cut -f1)
echo "    Size: $TARBALL_SIZE"

# --- Retention pruning ---

prune_dir() {
    local dir="$1"
    local keep="$2"
    local count
    count=$(find "$dir" -maxdepth 1 -name 'mtgc-*.tar.gz' | wc -l)
    if [ "$count" -gt "$keep" ]; then
        local to_remove=$((count - keep))
        echo "    Pruning $to_remove old backup(s) from $(basename "$dir")/ (keeping $keep)"
        find "$dir" -maxdepth 1 -name 'mtgc-*.tar.gz' -print0 \
            | sort -z \
            | head -z -n "$to_remove" \
            | xargs -0 rm -f
    fi
}

promote_oldest() {
    local src_dir="$1"
    local dst_dir="$2"
    local src_keep="$3"
    local src_count
    src_count=$(find "$src_dir" -maxdepth 1 -name 'mtgc-*.tar.gz' | wc -l)
    if [ "$src_count" -gt "$src_keep" ]; then
        local oldest
        oldest=$(find "$src_dir" -maxdepth 1 -name 'mtgc-*.tar.gz' -print0 \
            | sort -z \
            | head -z -n 1 \
            | tr '\0' '\n')
        if [ -n "$oldest" ]; then
            echo "    Promoting $(basename "$oldest") to $(basename "$dst_dir")/"
            mv "$oldest" "$dst_dir/"
        fi
    fi
}

# --- Optional S3 sync (runs BEFORE local pruning so we never delete the
#     only copy on a failed upload) ---

S3_SYNCED=false
if [ -n "${MTGC_BACKUP_S3_BUCKET:-}" ]; then
    if command -v aws &>/dev/null; then
        echo "==> Syncing to s3://${MTGC_BACKUP_S3_BUCKET}/mtgc-${INSTANCE}/..."
        if aws s3 sync "$INSTANCE_DIR" "s3://${MTGC_BACKUP_S3_BUCKET}/mtgc-${INSTANCE}/" \
                --exclude "staging/*"; then
            echo "    S3 sync complete."
            S3_SYNCED=true
        else
            echo "WARNING: S3 sync failed — keeping full local retention as fallback."
        fi
    else
        echo "WARNING: MTGC_BACKUP_S3_BUCKET is set but 'aws' CLI not found. Skipping S3 sync."
    fi
fi

# --- Retention pruning ---
#
# When S3 is the durable copy, keep a minimal local window for fast restore
# (defaults: 2 daily, 0 weekly, 0 monthly). Without S3, fall back to a full
# rolling 7/8/12 local-only window.
# Override any of these with MTGC_KEEP_DAILY / _WEEKLY / _MONTHLY env vars.

if [ "$S3_SYNCED" = "true" ]; then
    KEEP_DAILY="${MTGC_KEEP_DAILY:-2}"
    KEEP_WEEKLY="${MTGC_KEEP_WEEKLY:-0}"
    KEEP_MONTHLY="${MTGC_KEEP_MONTHLY:-0}"
else
    KEEP_DAILY="${MTGC_KEEP_DAILY:-7}"
    KEEP_WEEKLY="${MTGC_KEEP_WEEKLY:-8}"
    KEEP_MONTHLY="${MTGC_KEEP_MONTHLY:-12}"
fi

echo "==> Running retention pruning (daily=${KEEP_DAILY}, weekly=${KEEP_WEEKLY}, monthly=${KEEP_MONTHLY})..."

# Promote before pruning so we don't lose the oldest. Skip promotion when
# the destination tier is set to keep 0 — that would just move-then-delete.
if [ "$KEEP_MONTHLY" -gt 0 ]; then
    promote_oldest "$WEEKLY_DIR" "$MONTHLY_DIR" "$KEEP_WEEKLY"
fi
if [ "$KEEP_WEEKLY" -gt 0 ]; then
    promote_oldest "$DAILY_DIR" "$WEEKLY_DIR" "$KEEP_DAILY"
fi

prune_dir "$DAILY_DIR" "$KEEP_DAILY"
prune_dir "$WEEKLY_DIR" "$KEEP_WEEKLY"
prune_dir "$MONTHLY_DIR" "$KEEP_MONTHLY"

echo "==> Backup complete: $DAILY_DIR/$TARBALL_NAME"
