#!/usr/bin/env bash
#
# Tear down an MTGC container instance on macOS (no systemd).
# Stops and removes the container, removes the image.
# Data volume and env file are preserved unless --purge is passed.
#
# Usage:
#   bash deploy/mac-teardown.sh <instance>          # keep data
#   bash deploy/mac-teardown.sh <instance> --purge  # remove everything
#
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: bash deploy/mac-teardown.sh <instance> [--purge]"
    exit 1
fi

INSTANCE="$1"
PURGE="${2:-}"
CONTAINER_NAME="mtgc-${INSTANCE}"
VOLUME_NAME="${CONTAINER_NAME}-data"

echo "==> Tearing down $CONTAINER_NAME..."

# Stop and remove container
podman stop "$CONTAINER_NAME" 2>/dev/null || true
podman rm "$CONTAINER_NAME" 2>/dev/null || true
echo "    Container stopped and removed."

# Remove image
podman rmi "mtgc:${INSTANCE}" 2>/dev/null || true
echo "    Image removed."

if [ "$PURGE" = "--purge" ]; then
    # Remove data volume
    podman volume rm "$VOLUME_NAME" 2>/dev/null || true
    echo "    Data volume removed."

    # Remove env file
    rm -f "$HOME/.config/mtgc/${INSTANCE}.env"
    echo "    Env file removed."

    echo "==> Purge complete — all traces of $INSTANCE removed."
else
    echo "    Data volume and env file preserved."
    echo "    Run with --purge to remove everything."
fi
