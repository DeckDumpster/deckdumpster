#!/usr/bin/env bash
#
# Tear down an MTGC container instance.
# Stops the service, removes the Quadlet, and cleans up the image.
# Data volume and env file are preserved unless --purge is passed.
#
# Usage:
#   bash deploy/teardown.sh <instance>          # keep data
#   bash deploy/teardown.sh <instance> --purge  # remove everything
#
set -euo pipefail

# Ensure XDG_RUNTIME_DIR is set (required for systemctl --user).
# CI runners and non-interactive sessions often lack this.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

if [ $# -lt 1 ]; then
    echo "Usage: bash deploy/teardown.sh <instance> [--purge]"
    exit 1
fi

INSTANCE="$1"
PURGE="${2:-}"
SERVICE_NAME="mtgc-${INSTANCE}"
QUADLET_DIR="$HOME/.config/containers/systemd"
QUADLET_FILE="${QUADLET_DIR}/${SERVICE_NAME}.container"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$QUADLET_FILE" ]; then
    echo "ERROR: No Quadlet found for instance '$INSTANCE'"
    echo "    Expected: $QUADLET_FILE"
    exit 1
fi

# Remove from the store the instance was CREATED in, read from its Quadlet unit
# (de-3mo) — and read it before the unit is deleted below, since the unit is the
# only record. A teardown aimed at the wrong store would find nothing to remove,
# no-op through the `|| true` on every command, and then delete that record,
# stranding the image and volume with no way left to find them.
# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"
mtgc_store_adopt_instance "$INSTANCE"
mtgc_store_activate

echo "==> Tearing down $SERVICE_NAME..."

# Stop and disable timers
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
for PREFIX in mtgc-prices mtgc-sealed-catalog mtgc-backup mtgc-backup-check mtgc-catalog-check mtgc-diskcheck mtgc-edhrec; do
    systemctl --user stop "${PREFIX}-${INSTANCE}.timer" 2>/dev/null || true
    systemctl --user disable "${PREFIX}-${INSTANCE}.timer" 2>/dev/null || true
    rm -f "${SYSTEMD_USER_DIR}/${PREFIX}-${INSTANCE}.service" \
          "${SYSTEMD_USER_DIR}/${PREFIX}-${INSTANCE}.timer"
done
# The alert template has no timer of its own — it is only ever fired by an
# OnFailure=, so removing the units above leaves nothing that can start it.
rm -f "${SYSTEMD_USER_DIR}/mtgc-alert-${INSTANCE}@.service"

# Stop and disable
systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true

# Remove Quadlet
rm -f "$QUADLET_FILE"
systemctl --user daemon-reload

# Remove image
podman rmi "mtgc:${INSTANCE}" 2>/dev/null || true

echo "    Service stopped and Quadlet removed."

if [ "$PURGE" = "--purge" ]; then
    # Remove data volume
    podman volume rm "${SERVICE_NAME}-data" 2>/dev/null || true
    echo "    Data volume removed."

    # Remove env file
    rm -f "$HOME/.config/mtgc/${INSTANCE}.env"
    echo "    Env file removed."

    echo "==> Purge complete — all traces of $INSTANCE removed."
else
    echo "    Data volume and env file preserved."
    echo "    Run with --purge to remove everything."
fi
