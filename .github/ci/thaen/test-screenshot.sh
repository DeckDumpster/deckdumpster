#!/usr/bin/env bash
set -euo pipefail

# Test the screenshot pipeline end-to-end inside a container.
# Mirrors the entrypoint setup + the implement prompt's screenshot command.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

VM_CODE="/var/opt/dd-ci-code"
VM_DATA="/var/opt/dd-ci-data"

echo "Building dd-ci-server image..."
podman build -t dd-ci-server -f "$REPO_DIR/.github/containers/thaen/ci-server.containerfile" "$REPO_DIR"

echo "Running screenshot test..."
podman run --rm \
    -v "${VM_CODE}:/app:O" \
    -v "${VM_DATA}:/data:O" \
    --entrypoint bash dd-ci-server -c '
        uv sync --group dev 2>&1 | tail -1
        chown -R ci:ci /app /home/ci/.cache/uv
        cp /data/collection.sqlite /tmp/collection.sqlite
        chown ci:ci /tmp/collection.sqlite
        runuser -u ci -- bash -c '\''
            cd /app
            MTGC_DB=/tmp/collection.sqlite uv run mtg crack-pack-server --port 8555 &
            SERVER_PID=$!
            for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
                curl -sf http://localhost:8555/ > /dev/null 2>&1 && break
                sleep 1
            done
            mkdir -p /tmp/screenshots
            uv run shot-scraper "http://localhost:8555/" -o /tmp/screenshots/home.png
            kill $SERVER_PID 2>/dev/null
            ls -la /tmp/screenshots/home.png
        '\''
    '
