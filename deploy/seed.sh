#!/usr/bin/env bash
#
# Create a reusable seed data volume for fast instance bootstrapping.
# Runs `mtg setup --demo` once; new instances clone from this volume
# instead of repeating the 15-30 minute download.
#
# Usage:
#   bash deploy/seed.sh [--force]
#
# After seeding, `setup.sh --init` clones from this volume in seconds.
#
set -euo pipefail

SEED_VOLUME="mtgc-seed-data"
FORCE=false

for arg in "$@"; do
    case $arg in
        --force) FORCE=true ;;
        *)
            echo "Usage: bash deploy/seed.sh [--force]"
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

# The seed volume is not per-instance, so there is no unit to adopt: it belongs
# to whichever store the caller names. Unset means Podman's default store, as
# before (de-3mo). A seed volume built in an alternate store is only visible to
# `setup.sh --init` runs pointed at that same store.
# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"
mtgc_store_activate

if podman volume exists "$SEED_VOLUME" 2>/dev/null; then
    if [ "$FORCE" = "true" ]; then
        echo "==> Removing existing seed volume..."
        podman volume rm "$SEED_VOLUME"
    else
        echo "Seed volume '$SEED_VOLUME' already exists."
        echo "Use --force to recreate it."
        exit 0
    fi
fi

# Before writing another ~1 GB of layers, plus the seed volume itself: is
# there room? This build runs 15-30 minutes and creates a reusable volume, so
# it is exactly the disk-heavy path the gate exists for (de-yef).
bash "$SCRIPT_DIR/diskcheck.sh" --floor "${MTGC_STORE_ROOT:-$HOME}"

echo "==> Building container image (mtgc:latest)..."
podman build -t mtgc:latest -f Containerfile \
    -v "${HOME}/.cache/uv:/root/.cache/uv:z" .

echo "==> Creating seed volume ($SEED_VOLUME)..."
echo "    This runs 'mtg setup --demo' and downloads ~600 MB of data."
echo "    May take 15-30 minutes on first run."

podman run --rm \
    -v "${SEED_VOLUME}:/data:Z" \
    -e MTGC_HOME=/data \
    --entrypoint mtg \
    localhost/mtgc:latest \
    setup --demo

echo ""
echo "==> Seed volume ready!"
echo "    New instances using '--init' will clone from this volume (~seconds)."
echo "    Recreate with: bash deploy/seed.sh --force"
