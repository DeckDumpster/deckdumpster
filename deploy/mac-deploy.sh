#!/usr/bin/env bash
#
# Rebuild and restart a single MTGC instance on macOS (no systemd).
# Run from within the repo clone for this instance.
#
# Usage:
#   bash deploy/mac-deploy.sh <instance>
#
# Example:
#   bash deploy/mac-deploy.sh feature-xyz
#
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: bash deploy/mac-deploy.sh <instance>"
    echo "Example: bash deploy/mac-deploy.sh feature-xyz"
    exit 1
fi

INSTANCE="$1"
CONTAINER_NAME="mtgc-${INSTANCE}"
VOLUME_NAME="${CONTAINER_NAME}-data"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MTGC_CONFIG="$HOME/.config/mtgc"
ENV_FILE="${MTGC_CONFIG}/${INSTANCE}.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: No env file found for instance '$INSTANCE'"
    echo "    Expected: $ENV_FILE"
    echo "    Run mac-setup.sh first: bash deploy/mac-setup.sh $INSTANCE"
    exit 1
fi

echo "==> Building container image (mtgc:$INSTANCE)..."
podman build -t "mtgc:${INSTANCE}" -f "$REPO_DIR/Containerfile" "$REPO_DIR"

echo "==> Stopping old container..."
podman stop "$CONTAINER_NAME" 2>/dev/null || true
podman rm "$CONTAINER_NAME" 2>/dev/null || true

echo "==> Starting container ($CONTAINER_NAME)..."
podman run -d \
    --name "$CONTAINER_NAME" \
    --env-file "$ENV_FILE" \
    -e MTGC_HOME=/data \
    -p ":8081" \
    -v "${VOLUME_NAME}:/data" \
    "localhost/mtgc:${INSTANCE}"

# Discover the assigned port
sleep 2
PORT_LINE=$(podman port "$CONTAINER_NAME" 8081/tcp 2>/dev/null || true)
PORT=$(echo "$PORT_LINE" | cut -d: -f2 | head -1)
if [ -z "$PORT" ]; then
    echo "==> Could not determine port. Check: podman port $CONTAINER_NAME"
    exit 1
fi
echo "==> Listening on port $PORT"

MAX_ATTEMPTS=15
echo "==> Health check: $CONTAINER_NAME (port $PORT)..."
for i in $(seq 1 $MAX_ATTEMPTS); do
    if curl -skf --connect-timeout 3 "https://localhost:${PORT}/" > /dev/null 2>&1; then
        echo "==> Health check passed (attempt $i/$MAX_ATTEMPTS)"
        exit 0
    fi
    echo "    Attempt $i/$MAX_ATTEMPTS failed, waiting 2s..."
    sleep 2
done

echo "==> Health check FAILED after $MAX_ATTEMPTS attempts"
exit 1
