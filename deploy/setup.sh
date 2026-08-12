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
#   bash deploy/setup.sh <instance> [port] [--init] [--test] [--http-port <p>] [--tls-certs <dir>]
#
# Examples:
#   bash deploy/setup.sh prod 8081        # explicit port
#   bash deploy/setup.sh feature-xyz      # auto-assigns next free port
#   bash deploy/setup.sh test --init      # build + initialize data volume with demo data
#   bash deploy/setup.sh ui-test --test   # fast setup from pre-built fixture (~seconds)
#   bash deploy/setup.sh prod 8081 --http-port 8083   # also publish plain HTTP on 127.0.0.1:8083
#   bash deploy/setup.sh prod 8081 --tls-certs ~/.config/mtgc/certs   # mount host certs at /certs
#
# --http-port publishes the container's plaintext listener on the LOOPBACK
# interface only (127.0.0.1). It is for a host-local origin such as cloudflared;
# nothing off-host can reach it. Omit it and the generated unit is unchanged.
#
# --tls-certs mounts a host directory of externally-obtained certificates (e.g.
# from `tailscale cert`) at /certs inside the container, READ-ONLY. The app only
# ever reads them — point MTGC_TLS_CERT / MTGC_TLS_KEY in the instance env file
# at paths under /certs to use them. Omit it and the generated unit is unchanged.
#
# Both flags are STICKY: they are recorded in the instance env file as
# MTGC_HTTP_PUBLISH_PORT / MTGC_TLS_CERTS_DIR and re-applied when the flag is
# omitted, so deploy.sh regenerating a missing Quadlet reproduces the unit
# rather than silently dropping the publish and the mount. An explicit flag
# overrides the record; delete the line to drop the setting.
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
HTTP_PORT=""
TLS_CERTS=""
POSITIONAL=()
while [ $# -gt 0 ]; do
    case $1 in
        --init) INIT=true ;;
        --test) TEST=true ;;
        --http-port)
            if [ $# -lt 2 ]; then
                echo "ERROR: --http-port requires a port number"
                exit 1
            fi
            HTTP_PORT="$2"
            shift
            ;;
        --tls-certs)
            if [ $# -lt 2 ]; then
                echo "ERROR: --tls-certs requires a directory"
                exit 1
            fi
            TLS_CERTS="$2"
            shift
            ;;
        *) POSITIONAL+=("$1") ;;
    esac
    shift
done

if [ ${#POSITIONAL[@]} -lt 1 ]; then
    echo "Usage: bash deploy/setup.sh <instance> [port] [--init] [--test] [--http-port <p>] [--tls-certs <dir>]"
    echo "Example: bash deploy/setup.sh prod 8081"
    echo "         bash deploy/setup.sh test --init    # build + init data with demo dataset"
    echo "         bash deploy/setup.sh ui-test --test # fast setup from pre-built fixture"
    echo "         bash deploy/setup.sh prod 8081 --http-port 8083  # + plain HTTP on 127.0.0.1"
    echo "         bash deploy/setup.sh prod 8081 --tls-certs ~/.config/mtgc/certs  # + read-only certs at /certs"
    exit 1
fi

INSTANCE="${POSITIONAL[0]}"
SERVICE_NAME="mtgc-${INSTANCE}"
QUADLET_DIR="$HOME/.config/containers/systemd"
MTGC_CONFIG="$HOME/.config/mtgc"
ENV_FILE="${MTGC_CONFIG}/${INSTANCE}.env"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Recorded render inputs ---
#
# deploy.sh regenerates a missing Quadlet by re-running this script with the
# instance name and nothing else. --http-port and --tls-certs are inputs to the
# render, so unless they are recorded the regenerated unit silently loses both
# the plaintext publish and the cert mount. Record them in the instance env file
# — the same place MTGC_TLS_CERT / MTGC_TLS_KEY already live — and fall back to
# the recorded value when the flag is omitted. An explicit flag always wins; to
# drop a setting, delete its line from the env file and re-run.

recorded() {
    # Last assignment wins, matching how systemd reads an EnvironmentFile.
    [ -f "$ENV_FILE" ] || return 0
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -1
}

[ -n "$HTTP_PORT" ] || HTTP_PORT="$(recorded MTGC_HTTP_PUBLISH_PORT)"
[ -n "$TLS_CERTS" ] || TLS_CERTS="$(recorded MTGC_TLS_CERTS_DIR)"

# The directory must already exist: Podman would otherwise create it as an empty
# root-owned mount point and the container would start with no certificate to read.
if [ -n "$TLS_CERTS" ] && [ ! -d "${TLS_CERTS/#%h/$HOME}" ]; then
    echo "ERROR: --tls-certs directory does not exist: $TLS_CERTS"
    exit 1
fi

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
if [ -n "$HTTP_PORT" ]; then
    echo "    HTTP:     127.0.0.1:$HTTP_PORT (plaintext, loopback only)"
fi
if [ -n "$TLS_CERTS" ]; then
    echo "    Certs:    $TLS_CERTS -> /certs (read-only)"
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

# Record the render inputs resolved above so the next regeneration reproduces
# this unit. Rewriting in place (rather than mv) keeps the file's 600 mode.
record() {
    local key="$1" value="$2" tmp
    tmp="$(mktemp)"
    grep -v "^${key}=" "$ENV_FILE" > "$tmp" || true
    if [ -n "$value" ]; then
        echo "${key}=${value}" >> "$tmp"
    fi
    cat "$tmp" > "$ENV_FILE"
    rm -f "$tmp"
}

record MTGC_HTTP_PUBLISH_PORT "$HTTP_PORT"
record MTGC_TLS_CERTS_DIR "$TLS_CERTS"

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

bash "$REPO_DIR/deploy/render-quadlet.sh" \
    "$INSTANCE" "$PORT_MAPPING" "$HTTP_PORT" "$TLS_CERTS" \
    "$REPO_DIR/deploy/mtgc.container" > "$QUADLET_FILE"

# Conditionally mount shared reference volume if it exists.
# Skip for --test: test containers manage their own shared DB on the data volume.
SHARED_REF_VOL="mtgc-shared-ref"
if [ "$TEST" != "true" ] && podman volume exists "$SHARED_REF_VOL" 2>/dev/null; then
    sed -i '/^Volume=mtgc-.*-data/a Volume=mtgc-shared-ref:/shared:ro,z' "$QUADLET_FILE"
    sed -i '/^Environment=MTGC_HOME/a Environment=MTGC_SHARED_DB=/shared/shared.sqlite' "$QUADLET_FILE"
    echo "    Shared reference volume detected — MTGC_SHARED_DB enabled"
fi

## --- Generate and install timer units ---

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

for UNIT_PREFIX in mtgc-prices mtgc-sealed-catalog mtgc-backup mtgc-backup-check mtgc-edhrec; do
    echo "==> Installing ${UNIT_PREFIX} timer"
    for EXT in service timer; do
        sed -e "s|{{INSTANCE}}|${INSTANCE}|g" \
            -e "s|{{REPO_DIR}}|${REPO_DIR}|g" \
            "$REPO_DIR/deploy/${UNIT_PREFIX}.${EXT}" \
            > "${SYSTEMD_USER_DIR}/${UNIT_PREFIX}-${INSTANCE}.${EXT}"
    done
done

# The alert unit is a systemd instance template, not a timer: its %i is the name
# of the unit that failed, supplied by the OnFailure= that fires it. Rendered
# per MTGC instance like everything else, so setting up a test instance cannot
# repoint prod's alerting at a test checkout.
echo "==> Installing mtgc-alert template"
sed -e "s|{{INSTANCE}}|${INSTANCE}|g" \
    -e "s|{{REPO_DIR}}|${REPO_DIR}|g" \
    "$REPO_DIR/deploy/mtgc-alert@.service" \
    > "${SYSTEMD_USER_DIR}/mtgc-alert-${INSTANCE}@.service"

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
    podman cp "$temp:/data/shared.sqlite" "$staging/shared.sqlite" 2>/dev/null || true
    podman cp "$temp:/data/source_images" "$staging/source_images" 2>/dev/null \
        || mkdir -p "$staging/source_images"
    podman cp "$temp:/data/ingest_images" "$staging/ingest_images" 2>/dev/null \
        || mkdir -p "$staging/ingest_images"
    podman rm -f "$temp" >/dev/null

    # Include shared.sqlite in the tarball if it exists (after db split)
    local tar_files="collection.sqlite source_images ingest_images"
    [ -f "$staging/shared.sqlite" ] && tar_files="$tar_files shared.sqlite"
    tar czf "$tarball_path" -C "$staging" $tar_files
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

    # 1b. Split shared reference data onto the same volume (writable).
    # Production uses a separate read-only shared volume; test containers
    # keep everything on one volume so tests can write to any table.
    echo "==> Splitting shared reference data..."
    podman run --rm \
        -v "${TEMP_VOL}:/data:Z" \
        -e MTGC_HOME=/data \
        --entrypoint mtg \
        "$IMAGE" \
        db split --shared-out /data/shared.sqlite --prune

    # 2. Set MTGC_SHARED_DB BEFORE restore (restore starts the service)
    sed -i '/^Environment=MTGC_HOME/a Environment=MTGC_SHARED_DB=/data/shared.sqlite' "$QUADLET_FILE"
    systemctl --user daemon-reload

    # 3. Package into a backup tarball
    TARBALL=$(mktemp --suffix=.tar.gz)
    echo "==> Packaging data into backup tarball..."
    create_backup_tarball "$TEMP_VOL" "$IMAGE" "$TARBALL"
    podman volume rm "$TEMP_VOL" >/dev/null

    # 4. Restore from the tarball (exercises the full restore pipeline)
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
echo "  Bkp check:  systemctl --user enable --now mtgc-backup-check-${INSTANCE}.timer"
echo "  EDHREC:     systemctl --user enable --now mtgc-edhrec-${INSTANCE}.timer"
echo "  Teardown:   bash deploy/teardown.sh $INSTANCE"
