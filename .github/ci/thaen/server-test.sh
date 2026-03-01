#!/usr/bin/env bash
set -euo pipefail

# Quick smoke test: build image, start server in container, verify HTTP 200.
# No API key — validates the server starts without ANTHROPIC_API_KEY.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

VM_CODE="/var/opt/dd-ci-code"
VM_DATA="/var/opt/dd-ci-data"

echo "Building dd-ci-server image..."
podman build -t dd-ci-server -f "$REPO_DIR/.github/containers/thaen/ci-server.containerfile" "$REPO_DIR"

echo "Starting server in container..."
podman run --rm \
    -v "${VM_CODE}:/app:O" \
    -v "${VM_DATA}:/data:O" \
    --entrypoint bash dd-ci-server -c '
        uv sync --group dev 2>&1 | tail -1
        chown -R ci:ci /app /home/ci/.cache/uv
        cp /data/collection.sqlite /tmp/collection.sqlite
        chown ci:ci /tmp/collection.sqlite
        runuser -u ci -- env MTGC_DB=/tmp/collection.sqlite uv run mtg crack-pack-server --port 8555 &
        for i in $(seq 1 15); do curl -ksf https://localhost:8555/ > /dev/null 2>&1 && break; sleep 1; done
        STATUS=$(curl -ks -o /dev/null -w "%{http_code}" https://localhost:8555/)
        if [ "$STATUS" = "200" ]; then
            echo "Server started OK (HTTP $STATUS)"
            exit 0
        else
            echo "Server failed (HTTP $STATUS)" >&2
            exit 1
        fi
    '
