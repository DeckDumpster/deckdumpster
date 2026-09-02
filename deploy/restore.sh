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

# Restore into the store the instance lives in (de-3mo). setup.sh calls this as
# a child and PATH already carries its shim, so this is a no-op there; it is
# here for the standalone case, where a restore into the wrong store would
# create a SECOND, empty data volume and then start the instance against the
# original one — reporting success over data it never touched.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"
mtgc_store_adopt_instance "$INSTANCE"
mtgc_store_activate

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

# An archive with no shared.sqlite landing on a split volume would leave a
# restored collection beside whatever catalogue happened to be there, and the
# instance would serve it: under split-DB every shared table is a temp view over
# that file, so the mismatch is invisible from the collection side and the
# restore reports OK. Refuse instead. This is what a tarball written before
# de-hal looks like — backup.sh archived collection.sqlite and nothing else, so
# every backup of a split instance taken until then is one of these.
if [ ! -f "$STAGING_DIR/shared.sqlite" ] \
        && podman exec "$TEMP_CONTAINER" sh -c '[ -f /data/shared.sqlite ]'; then
    echo "ERROR: $VOLUME_NAME is split (it has shared.sqlite) but this backup has none."
    echo "    Restoring it would leave the new collection beside the old catalogue."
    echo "    Restore a backup taken after de-hal, or delete /data/shared.sqlite from"
    echo "    the volume first to restore this instance as monolithic."
    exit 1
fi

# Copy database
echo "    Restoring collection.sqlite..."
podman cp "$STAGING_DIR/collection.sqlite" "$TEMP_CONTAINER:/data/collection.sqlite"

# The reference catalogue of a split instance (cards, printings, sets, and the
# append-only price series). Absent from a monolithic instance's archive, where
# collection.sqlite holds those tables itself.
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
import os, sqlite3
db = sqlite3.connect('/data/collection.sqlite')
# Quick integrity check
result = db.execute('PRAGMA integrity_check').fetchone()[0]
if result != 'ok':
    print(f'INTEGRITY CHECK FAILED: {result}')
    exit(1)
# Count collections as a sanity check
count = db.execute('SELECT COUNT(*) FROM collection').fetchone()[0]
db.close()
# On a split instance the catalogue the app actually serves is in the second
# file, and an empty one reads as a healthy instance with no cards in the world.
shared = '/data/shared.sqlite'
if os.path.exists(shared):
    sh = sqlite3.connect(shared)
    result = sh.execute('PRAGMA integrity_check').fetchone()[0]
    if result != 'ok':
        print(f'SHARED INTEGRITY CHECK FAILED: {result}')
        exit(1)
    printings = sh.execute('SELECT COUNT(*) FROM printings').fetchone()[0]
    sh.close()
    print(f'OK — {count} collection entries, {printings} shared printings')
else:
    print(f'OK — {count} collection entries')
" 2>&1)

echo "    $VERIFY_RESULT"

echo "==> Restore complete!"
echo "    Instance '$INSTANCE' is running with restored data."
echo "    Check: systemctl --user status $SERVICE_NAME"
