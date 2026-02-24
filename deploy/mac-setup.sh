#!/usr/bin/env bash
#
# Set up an MTGC container instance on macOS (rootless Podman, no systemd).
# Run from within the repo clone for this instance.
#
# Prerequisites:
#   brew install podman
#   podman machine init && podman machine start
#
# Usage:
#   bash deploy/mac-setup.sh <instance> [--init] [--test]
#
# Examples:
#   bash deploy/mac-setup.sh feature-xyz
#   bash deploy/mac-setup.sh test --init      # build + initialize data volume with demo data
#   bash deploy/mac-setup.sh ui-test --test   # fast setup from pre-built fixture (~seconds)
#
# Container naming:
#   Image:     mtgc:<instance>
#   Container: mtgc-<instance>
#   Volume:    mtgc-<instance>-data
#   Env:       ~/.config/mtgc/<instance>.env
#
set -euo pipefail

# --- Parse arguments ---

INIT=false
TEST=false
POSITIONAL=()
for arg in "$@"; do
    case $arg in
        --init) INIT=true ;;
        --test) TEST=true ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done

if [ ${#POSITIONAL[@]} -lt 1 ]; then
    echo "Usage: bash deploy/mac-setup.sh <instance> [--init] [--test]"
    echo "Example: bash deploy/mac-setup.sh test --init"
    echo "         bash deploy/mac-setup.sh ui-test --test   # fast setup from pre-built fixture"
    exit 1
fi

INSTANCE="${POSITIONAL[0]}"
CONTAINER_NAME="mtgc-${INSTANCE}"
VOLUME_NAME="${CONTAINER_NAME}-data"
MTGC_CONFIG="$HOME/.config/mtgc"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> MTGC macOS setup"
echo "    Instance:  $INSTANCE"
echo "    Container: $CONTAINER_NAME"
echo "    Repo:      $REPO_DIR"

# --- Prerequisites ---

if ! command -v podman &>/dev/null; then
    echo "ERROR: podman not found. Install it first:"
    echo "  brew install podman"
    exit 1
fi

echo "    podman: $(podman --version)"

# --- Env file ---

ENV_FILE="${MTGC_CONFIG}/${INSTANCE}.env"
if [ ! -f "$ENV_FILE" ]; then
    mkdir -p "$MTGC_CONFIG"
    if [ -f "${MTGC_CONFIG}/default.env" ]; then
        echo "==> Creating $ENV_FILE from default.env..."
        cp "${MTGC_CONFIG}/default.env" "$ENV_FILE"
    else
        echo "==> Creating $ENV_FILE from .env.example..."
        echo "    NOTE: Set ANTHROPIC_API_KEY in $ENV_FILE before starting."
        echo "    (Create ~/.config/mtgc/default.env to skip this for future instances.)"
        cp "$REPO_DIR/.env.example" "$ENV_FILE"
    fi
    chmod 600 "$ENV_FILE"
else
    echo "    $ENV_FILE already exists, skipping"
fi

# --- Build container image ---

echo "==> Building container image (mtgc:$INSTANCE)..."
podman build -t "mtgc:${INSTANCE}" -f "$REPO_DIR/Containerfile" "$REPO_DIR"

# --- Optional: initialize data volume ---

if [ "$TEST" = "true" ]; then
    echo "==> Initializing data volume ($VOLUME_NAME) from pre-built fixture..."
    podman run --rm \
        -v "${VOLUME_NAME}:/data" \
        -e MTGC_HOME=/data \
        --entrypoint mtg \
        "localhost/mtgc:${INSTANCE}" \
        setup --demo --from-fixture /app/test-data.sqlite
elif [ "$INIT" = "true" ]; then
    echo "==> Initializing data volume ($VOLUME_NAME) with demo dataset..."
    echo "    This downloads ~600 MB of MTGJSON data and caches Scryfall cards."
    echo "    May take 15-30 minutes on first run."
    podman run --rm \
        -v "${VOLUME_NAME}:/data" \
        -e MTGC_HOME=/data \
        --entrypoint mtg \
        "localhost/mtgc:${INSTANCE}" \
        setup --demo
fi

# --- Start the container ---

# Stop any existing container with this name
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

echo ""
echo "==> Setup complete!"
echo ""
if [ -n "$PORT" ]; then
    echo "    URL:        https://localhost:${PORT}"
fi
echo "    Port:       podman port $CONTAINER_NAME 8081/tcp"
echo "    Logs:       podman logs -f $CONTAINER_NAME"
echo "    Stop:       podman stop $CONTAINER_NAME"
echo "    Start:      podman start $CONTAINER_NAME"
echo "    Teardown:   bash deploy/mac-teardown.sh $INSTANCE"
