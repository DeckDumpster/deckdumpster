#!/usr/bin/env bash
#
# Restore an MTGC instance from a backup tarball.
# Stops the instance, replaces data, restarts, and verifies integrity.
#
# Usage:
#   bash deploy/restore.sh [--yes] <backup-file.tar.gz> [instance]
#
# Options:
#   --yes, -y   Skip confirmation prompt (for automated/scripted use)
#
# Examples:
#   bash deploy/restore.sh ~/mtgc-backups/prod/daily/mtgc-prod-20260303-020000.tar.gz prod
#   bash deploy/restore.sh --yes ~/mtgc-backups/prod/daily/mtgc-prod-20260303-020000.tar.gz prod
#
set -euo pipefail

# Ensure XDG_RUNTIME_DIR is set (required for systemctl --user).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# --- Parse arguments ---

YES=false
POSITIONAL=()
for arg in "$@"; do
    case $arg in
        --yes|-y) YES=true ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done

if [ ${#POSITIONAL[@]} -lt 1 ]; then
    echo "Usage: bash deploy/restore.sh [--yes] <backup-file.tar.gz> [instance]"
    echo "Example: bash deploy/restore.sh ~/mtgc-backups/prod/daily/mtgc-prod-20260303-020000.tar.gz prod"
    exit 1
fi

BACKUP_FILE="${POSITIONAL[0]}"
INSTANCE="${POSITIONAL[1]:-prod}"
SERVICE_NAME="mtgc-${INSTANCE}"
CONTAINER="systemd-${SERVICE_NAME}"
VOLUME_NAME="${SERVICE_NAME}-data"

echo "==> MTGC restore"
echo "    Backup:    $BACKUP_FILE"
echo "    Instance:  $INSTANCE"
echo "    Service:   $SERVICE_NAME"
echo "    Volume:    $VOLUME_NAME"

# --- Validate backup file ---

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Quick sanity check — tarball should contain our expected files
TARBALL_CONTENTS=$(tar tzf "$BACKUP_FILE" 2>/dev/null || true)
if ! echo "$TARBALL_CONTENTS" | grep -q "collection.sqlite"; then
    echo "ERROR: Backup tarball does not contain collection.sqlite"
    echo "    This doesn't look like a valid MTGC backup."
    exit 1
fi

echo "    Backup file validated."

# --- Confirm with user ---

if [ "$YES" = "false" ]; then
    echo ""
    echo "WARNING: This will replace ALL data for instance '$INSTANCE'."
    echo "    The current database and images will be overwritten."
    echo ""
    read -r -p "Continue? [y/N] " response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "Restore cancelled."
        exit 0
    fi
fi

# --- Stop the instance ---

echo "==> Stopping $SERVICE_NAME..."
systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
sleep 2

# --- Extract backup to staging ---

STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT

echo "==> Extracting backup..."
tar xzf "$BACKUP_FILE" -C "$STAGING_DIR"

# --- Restore data into volume ---
# Use a temporary container to mount the volume and copy data in.

TEMP_CONTAINER="mtgc-restore-$$"

echo "==> Restoring data to volume $VOLUME_NAME..."

# Create volume if it doesn't exist (e.g., restoring to a fresh instance)
podman volume create "$VOLUME_NAME" >/dev/null 2>&1 || true

# Start a temporary container with the volume mounted
podman run -d --name "$TEMP_CONTAINER" \
    -v "${VOLUME_NAME}:/data:Z" \
    --entrypoint sleep \
    localhost/mtgc:latest infinity >/dev/null

# Clean up temp container on exit
cleanup() {
    podman rm -f "$TEMP_CONTAINER" >/dev/null 2>&1 || true
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

# Copy database
echo "    Restoring collection.sqlite..."
podman cp "$STAGING_DIR/collection.sqlite" "$TEMP_CONTAINER:/data/collection.sqlite"

# Copy shared database if present (from db split)
if [ -f "$STAGING_DIR/shared.sqlite" ]; then
    echo "    Restoring shared.sqlite..."
    podman cp "$STAGING_DIR/shared.sqlite" "$TEMP_CONTAINER:/data/shared.sqlite"
fi

# Copy images (remove existing first to avoid stale files)
echo "    Restoring source_images/..."
podman exec "$TEMP_CONTAINER" rm -rf /data/source_images
podman cp "$STAGING_DIR/source_images" "$TEMP_CONTAINER:/data/source_images"

echo "    Restoring ingest_images/..."
podman exec "$TEMP_CONTAINER" rm -rf /data/ingest_images
podman cp "$STAGING_DIR/ingest_images" "$TEMP_CONTAINER:/data/ingest_images"

# Stop and remove temporary container
podman rm -f "$TEMP_CONTAINER" >/dev/null

# --- Restart the instance ---

echo "==> Starting $SERVICE_NAME..."
systemctl --user start "$SERVICE_NAME"
sleep 3

# --- Verify integrity ---

echo "==> Verifying database integrity..."
VERIFY_RESULT=$(podman exec "$CONTAINER" python3 -c "
import sqlite3
db = sqlite3.connect('/data/collection.sqlite')
# Quick integrity check
result = db.execute('PRAGMA integrity_check').fetchone()[0]
if result != 'ok':
    print(f'INTEGRITY CHECK FAILED: {result}')
    exit(1)
# Count collections as a sanity check
count = db.execute('SELECT COUNT(*) FROM collection').fetchone()[0]
print(f'OK — {count} collection entries')
db.close()
" 2>&1)

echo "    $VERIFY_RESULT"

echo "==> Restore complete!"
echo "    Instance '$INSTANCE' is running with restored data."
echo "    Check: systemctl --user status $SERVICE_NAME"
