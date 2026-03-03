#!/usr/bin/env bash
#
# Set up an MTGC container instance (rootless Podman).
# No sudo required — runs entirely as the current user.
# Run from within the repo clone for this instance.
#
# Prerequisites (one-time, requires sudo):
#   sudo apt install podman
#   loginctl enable-linger $USER
#
# Usage:
#   bash deploy/setup.sh <instance> [port] [--init] [--test]
#
# Examples:
#   bash deploy/setup.sh prod 8081        # explicit port
#   bash deploy/setup.sh feature-xyz      # auto-assigns next free port
#   bash deploy/setup.sh test --init      # build + initialize data volume with demo data
#   bash deploy/setup.sh ui-test --test   # fast setup from pre-built fixture (~seconds)
#
# Env file:
#   Copies from ~/.config/mtgc/default.env if it exists (set this up once
#   with your API key). Falls back to .env.example (needs manual editing).
#
set -euo pipefail

# Ensure XDG_RUNTIME_DIR is set (required for systemctl --user).
# CI runners and non-interactive sessions often lack this.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

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
    echo "Usage: bash deploy/setup.sh <instance> [port] [--init] [--test]"
    echo "Example: bash deploy/setup.sh prod 8081"
    echo "         bash deploy/setup.sh test --init    # build + init data with demo dataset"
    echo "         bash deploy/setup.sh ui-test --test # fast setup from pre-built fixture"
    exit 1
fi

INSTANCE="${POSITIONAL[0]}"
SERVICE_NAME="mtgc-${INSTANCE}"
QUADLET_DIR="$HOME/.config/containers/systemd"
MTGC_CONFIG="$HOME/.config/mtgc"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Port assignment ---

if [ ${#POSITIONAL[@]} -ge 2 ]; then
    PORT="${POSITIONAL[1]}"
else
    # Let the OS assign an available port at container start
    PORT=0
fi

echo "==> MTGC deployment setup"
echo "    Instance: $INSTANCE"
if [ "$PORT" = "0" ]; then
    echo "    Port:     (auto-assign)"
else
    echo "    Port:     $PORT"
fi
echo "    Service:  $SERVICE_NAME"
echo "    Repo:     $REPO_DIR"

# --- Prerequisites ---

if ! command -v podman &>/dev/null; then
    echo "ERROR: podman not found. Install it first:"
    echo "  sudo apt install podman"
    exit 1
fi

echo "    podman: $(podman --version)"

if ! loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q "Linger=yes"; then
    echo "WARNING: linger not enabled — services will stop when you log out."
    echo "  Fix with: loginctl enable-linger $USER  (may need sudo)"
fi

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

echo "==> Building container image (mtgc:latest)..."
podman build -t mtgc:latest -f "$REPO_DIR/Containerfile" \
    -v "${HOME}/.cache/uv:/root/.cache/uv:z" "$REPO_DIR"
podman tag mtgc:latest "mtgc:${INSTANCE}"

# --- Generate and install Quadlet ---

QUADLET_FILE="${QUADLET_DIR}/${SERVICE_NAME}.container"
echo "==> Installing Quadlet: $QUADLET_FILE"
mkdir -p "$QUADLET_DIR"

# When PORT=0 (auto-assign), use ":8081" so Podman picks an available host port.
# Otherwise use "PORT:8081" to bind a specific host port.
if [ "$PORT" = "0" ]; then
    PORT_MAPPING=":8081"
else
    PORT_MAPPING="${PORT}:8081"
fi

sed \
    -e "s|{{INSTANCE}}|${INSTANCE}|g" \
    -e "s|{{PORT}}:8081|${PORT_MAPPING}|g" \
    "$REPO_DIR/deploy/mtgc.container" > "$QUADLET_FILE"

## --- Generate and install timer units ---

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

for UNIT_PREFIX in mtgc-prices mtgc-sealed-catalog mtgc-backup; do
    echo "==> Installing ${UNIT_PREFIX} timer"
    for EXT in service timer; do
        sed -e "s|{{INSTANCE}}|${INSTANCE}|g" \
            "$REPO_DIR/deploy/${UNIT_PREFIX}.${EXT}" \
            > "${SYSTEMD_USER_DIR}/${UNIT_PREFIX}-${INSTANCE}.${EXT}"
    done
done

systemctl --user daemon-reload

# --- Optional: initialize data volume (always exercises restore.sh) ---

# Helper: package backup-able data from a volume into a tarball.
# Extracts collection.sqlite, source_images/, and ingest_images/.
create_backup_tarball() {
    local volume="$1"
    local image="$2"
    local tarball_path="$3"
    local staging
    staging=$(mktemp -d)
    local temp="mtgc-export-$$"

    podman run -d --name "$temp" \
        -v "${volume}:/data:Z" \
        --entrypoint sleep "$image" infinity >/dev/null

    podman cp "$temp:/data/collection.sqlite" "$staging/collection.sqlite"
    podman cp "$temp:/data/source_images" "$staging/source_images" 2>/dev/null \
        || mkdir -p "$staging/source_images"
    podman cp "$temp:/data/ingest_images" "$staging/ingest_images" 2>/dev/null \
        || mkdir -p "$staging/ingest_images"
    podman rm -f "$temp" >/dev/null

    tar czf "$tarball_path" -C "$staging" collection.sqlite source_images ingest_images
    rm -rf "$staging"
}

RESTORED=false

if [ "$TEST" = "true" ]; then
    VOLUME_NAME="${SERVICE_NAME}-data"
    TEMP_VOL="${VOLUME_NAME}-setup"
    IMAGE="localhost/mtgc:${INSTANCE}"

    echo "==> Initializing data from fixture via backup/restore pipeline..."

    # 1. Populate a temporary volume with fixture + sample data
    podman volume create "$TEMP_VOL" >/dev/null 2>&1 || true
    podman run --rm \
        -v "${TEMP_VOL}:/data:Z" \
        -e MTGC_HOME=/data \
        --entrypoint mtg \
        "$IMAGE" \
        setup --demo --from-fixture /app/test-data.sqlite
    podman run --rm \
        -v "${TEMP_VOL}:/data:Z" \
        -e MTGC_HOME=/data \
        --entrypoint mtg \
        "$IMAGE" \
        sample-ingest

    # 2. Package into a backup tarball
    TARBALL=$(mktemp --suffix=.tar.gz)
    echo "==> Packaging data into backup tarball..."
    create_backup_tarball "$TEMP_VOL" "$IMAGE" "$TARBALL"
    podman volume rm "$TEMP_VOL" >/dev/null

    # 3. Restore from the tarball (exercises the full restore pipeline)
    bash "$REPO_DIR/deploy/restore.sh" --yes "$TARBALL" "$INSTANCE"
    rm -f "$TARBALL"
    RESTORED=true

elif [ "$INIT" = "true" ]; then
    VOLUME_NAME="${SERVICE_NAME}-data"
    SEED_VOLUME="mtgc-seed-data"
    IMAGE="localhost/mtgc:${INSTANCE}"

    if podman volume exists "$SEED_VOLUME" 2>/dev/null; then
        echo "==> Cloning seed volume to $VOLUME_NAME..."
        podman volume create "$VOLUME_NAME" >/dev/null 2>&1 || true
        podman volume export "$SEED_VOLUME" | podman volume import "$VOLUME_NAME" -
        echo "    Done (cloned from seed volume)."
    else
        echo "==> No seed volume found — running full setup (slow)..."
        echo "    TIP: Run 'bash deploy/seed.sh' once to create a reusable seed volume."
        echo "    This downloads ~600 MB of MTGJSON data and caches Scryfall cards."
        echo "    May take 15-30 minutes on first run."
        podman volume create "$VOLUME_NAME" >/dev/null 2>&1 || true
        podman run --rm \
            -v "${VOLUME_NAME}:/data:Z" \
            -e MTGC_HOME=/data \
            --entrypoint mtg \
            "$IMAGE" \
            setup --demo
    fi

    # Round-trip through backup/restore to exercise the restore pipeline.
    # Non-backup data (AllPrintings.json, Scryfall cache) stays on the volume
    # untouched — restore only overwrites collection.sqlite and image dirs.
    TARBALL=$(mktemp --suffix=.tar.gz)
    echo "==> Exercising backup/restore pipeline..."
    create_backup_tarball "$VOLUME_NAME" "$IMAGE" "$TARBALL"
    bash "$REPO_DIR/deploy/restore.sh" --yes "$TARBALL" "$INSTANCE"
    rm -f "$TARBALL"
    RESTORED=true
fi

echo ""
echo "==> Setup complete!"
echo ""
if [ "$RESTORED" = "true" ]; then
    echo "  Status:     running (started during restore)"
    echo "  Port:       podman port systemd-${SERVICE_NAME}"
else
    echo "  Start:      systemctl --user start $SERVICE_NAME"
    echo "  Port:       podman port systemd-${SERVICE_NAME}"
    echo "  Init data:  podman exec -it systemd-${SERVICE_NAME} mtg setup"
fi
echo "  Logs:       journalctl --user -u $SERVICE_NAME -f"
echo "  Prices:     systemctl --user enable --now mtgc-prices-${INSTANCE}.timer"
echo "  Sealed:     systemctl --user enable --now mtgc-sealed-catalog-${INSTANCE}.timer"
echo "  Backup:     systemctl --user enable --now mtgc-backup-${INSTANCE}.timer"
echo "  Teardown:   bash deploy/teardown.sh $INSTANCE"
