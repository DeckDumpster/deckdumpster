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
# Retention:
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
CONTAINER="systemd-mtgc-${INSTANCE}"
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
echo "    Container: $CONTAINER"
echo "    Backup to: $INSTANCE_DIR"

# --- Ensure directories exist ---

mkdir -p "$DAILY_DIR" "$WEEKLY_DIR" "$MONTHLY_DIR"

# --- Verify container is running ---

if ! podman container exists "$CONTAINER" 2>/dev/null; then
    echo "ERROR: Container '$CONTAINER' not found."
    echo "    Is the instance running? systemctl --user start mtgc-${INSTANCE}"
    exit 1
fi

if [ "$(podman inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
    echo "ERROR: Container '$CONTAINER' exists but is not running."
    exit 1
fi

# --- Create staging area ---

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
trap 'rm -rf "$STAGING_DIR"' EXIT

# --- Snapshot SQLite database ---

echo "==> Creating SQLite snapshot..."
podman exec "$CONTAINER" python3 -c "
import sqlite3, sys
src = sqlite3.connect('/data/collection.sqlite')
dst = sqlite3.connect('/tmp/mtgc_backup.sqlite')
src.backup(dst)
dst.close()
src.close()
print('Snapshot created successfully')
"

echo "==> Copying database snapshot out..."
podman cp "$CONTAINER:/tmp/mtgc_backup.sqlite" "$STAGING_DIR/collection.sqlite"
podman exec "$CONTAINER" rm -f /tmp/mtgc_backup.sqlite

# --- Copy images ---

echo "==> Copying source_images..."
podman cp "$CONTAINER:/data/source_images" "$STAGING_DIR/source_images" 2>/dev/null || {
    echo "    (no source_images directory — skipping)"
    mkdir -p "$STAGING_DIR/source_images"
}

echo "==> Copying ingest_images..."
podman cp "$CONTAINER:/data/ingest_images" "$STAGING_DIR/ingest_images" 2>/dev/null || {
    echo "    (no ingest_images directory — skipping)"
    mkdir -p "$STAGING_DIR/ingest_images"
}

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

echo "==> Running retention pruning..."

# Promote before pruning so we don't lose the oldest
promote_oldest "$WEEKLY_DIR" "$MONTHLY_DIR" 8
promote_oldest "$DAILY_DIR" "$WEEKLY_DIR" 7

prune_dir "$DAILY_DIR" 7
prune_dir "$WEEKLY_DIR" 8
prune_dir "$MONTHLY_DIR" 12

# --- Optional S3 sync ---

if [ -n "${MTGC_BACKUP_S3_BUCKET:-}" ]; then
    if command -v aws &>/dev/null; then
        echo "==> Syncing to s3://${MTGC_BACKUP_S3_BUCKET}/mtgc-${INSTANCE}/..."
        aws s3 sync "$INSTANCE_DIR" "s3://${MTGC_BACKUP_S3_BUCKET}/mtgc-${INSTANCE}/" \
            --exclude "staging/*"
        echo "    S3 sync complete."
    else
        echo "WARNING: MTGC_BACKUP_S3_BUCKET is set but 'aws' CLI not found. Skipping S3 sync."
    fi
fi

echo "==> Backup complete: $DAILY_DIR/$TARBALL_NAME"
