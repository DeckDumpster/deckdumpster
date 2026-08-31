#!/usr/bin/env bash
#
# Rebuild and restart a single MTGC instance.
# Run from within the repo clone for this instance.
#
# Usage:
#   bash deploy/deploy.sh <instance>
#
# Example:
#   bash deploy/deploy.sh prod
#
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: bash deploy/deploy.sh <instance>"
    echo "Example: bash deploy/deploy.sh prod"
    exit 1
fi

INSTANCE="$1"
SERVICE_NAME="mtgc-${INSTANCE}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

# Ensure XDG_RUNTIME_DIR is set (required for systemctl --user).
# CI runners and non-interactive sessions often lack this.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# Build into the store this instance actually lives in, read from its Quadlet
# unit (de-3mo). Without this, a deploy run from a shell that had activated an
# alternate store would build and tag there while the unstamped unit kept
# systemd on the default store — the restart succeeds and goes on serving the
# OLD image. prod's unit carries no store, so prod builds where it always did.
# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"
mtgc_store_adopt_instance "$INSTANCE"
mtgc_store_activate

QUADLET_FILE="$HOME/.config/containers/systemd/${SERVICE_NAME}.container"

# Nothing else may write MTGC build images to Podman's default store while this
# build runs. Prod builds there — that is the disk it runs from — and since
# 4c5d9b2 gave deploys their own runner on the same box, a PR's
# store-isolation-gate.sh run overlaps this one. On 2026-08-30 21:38 the gate
# read three of this build's in-flight layers as a leak and `podman rmi -f`'d
# them mid-build; the deploy died with "layer not known" and that merge never
# reached prod. See mtgc_default_store_lock in store-lib.sh for why the two
# cannot be told apart after the fact.
#
# Only when this instance builds into the DEFAULT store. A non-prod instance has
# a store of its own, contends with nobody, and should not queue behind CI.
#
# Failing here is deliberate, and it is the one place this script prefers a red
# deploy to a completed one: the alternative is building on layers a gate is
# about to delete, which is the exact failure above and produces a deploy that
# reports success while prod serves the old image. The default 30 minutes is
# roughly six gate runs, so reaching it means the lock is held by something
# stuck rather than something working.
HELD_STORE_LOCK=false
DEPLOY_LOCK_TIMEOUT="${MTGC_DEPLOY_LOCK_TIMEOUT:-1800}"
if [ -z "${MTGC_STORE_ROOT:-}" ]; then
    echo "==> Waiting for the default-store build lock..."
    if mtgc_default_store_lock "$DEPLOY_LOCK_TIMEOUT"; then
        HELD_STORE_LOCK=true
    else
        echo "==> DEPLOY FAILED: no default-store build lock after ${DEPLOY_LOCK_TIMEOUT}s." >&2
        echo "    Something else is writing MTGC images to ${HOME}/.local/share/containers." >&2
        echo "    Lock: $MTGC_DEFAULT_STORE_LOCK_FILE" >&2
        if command -v fuser >/dev/null 2>&1; then
            echo "    Held by: $(fuser "$MTGC_DEFAULT_STORE_LOCK_FILE" 2>&1 | tr -d '\n')" >&2
        fi
        exit 1
    fi
fi

# If Quadlet doesn't exist yet, delegate to setup.sh for initial install.
# Passing only the instance name is safe: setup.sh reloads --http-port,
# --tls-certs and the explicit HTTPS host port from MTGC_HTTP_PUBLISH_PORT /
# MTGC_TLS_CERTS_DIR / MTGC_PUBLISH_PORT in the instance env file, so a
# regenerated unit keeps the plaintext publish, the cert mount and the port it
# was created on instead of silently dropping them. The port matters most
# quietly of the three: the health check below discovers the port from
# `podman port`, so a moved instance still reports healthy.
if [ ! -f "$QUADLET_FILE" ]; then
    echo "==> No Quadlet found for $INSTANCE, running initial setup..."
    bash "$SCRIPT_DIR/setup.sh" "$INSTANCE"
    echo "==> Starting $SERVICE_NAME..."
    systemctl --user start "$SERVICE_NAME"
else
    # Before writing another ~1 GB of layers: is there room? This is prod's
    # redeploy path, so a build that runs out mid-way leaves a partial image and
    # then restarts the live service against it. Gated on the store adopted
    # above — prod's unit carries none, so prod measures the disk it runs from.
    # There is no bypass flag; MTGC_DISK_FLOOR_GB is the only knob (de-yef).
    bash "$SCRIPT_DIR/diskcheck.sh" --floor "${MTGC_STORE_ROOT:-$HOME}"

    echo "==> Building container image (mtgc:latest)..."
    podman build -t mtgc:latest -f Containerfile \
        -v "${HOME}/.cache/uv:/root/.cache/uv:z" .
    podman tag mtgc:latest "mtgc:${INSTANCE}"

    # Reinstall the timer units from this checkout. deploy.sh runs setup.sh
    # only when the Quadlet is missing (above), so for an instance that already
    # exists this is the ONLY path a unit added to the repo can travel — and
    # without it, it travelled none. prod ran for months with
    # mtgc-catalog-check, mtgc-catalog-refresh and mtgc-diskcheck absent from
    # the host entirely, each of them a feature that had landed on main and
    # deployed (de-46k).
    #
    # Unconditional because it is safe to be: it rewrites unit files, never
    # enable state, so an armed timer stays armed and a disarmed one stays
    # disarmed. Arming is still a per-instance decision made once, by hand.
    echo "==> Installing timer units from this checkout..."
    # shellcheck source=deploy/units-lib.sh
    . "$SCRIPT_DIR/units-lib.sh"
    # Ends in `systemctl --user daemon-reload`, which is also what picks up any
    # Quadlet change — hence no second reload here.
    mtgc_install_units "$INSTANCE" "$REPO_DIR"

    echo "==> Restarting $SERVICE_NAME..."
    systemctl --user restart "$SERVICE_NAME"

    # Reclaim disk from the previous image layers. Each build leaves the
    # prior `mtgc:latest` content dangling once the tag moves. Without this
    # the host accumulates ~1 GB per deploy and eventually fills the disk,
    # which is what historically broke nightly backups (no room to stage
    # the SQLite snapshot).
    echo "==> Pruning dangling images..."
    podman image prune -f >/dev/null 2>&1 || true
fi

# Everything that writes to the store is done; the health check below only reads
# over HTTP. Holding the lock through it would queue a gate run behind a curl
# loop for no reason.
if [ "$HELD_STORE_LOCK" = true ]; then
    mtgc_default_store_unlock
    HELD_STORE_LOCK=false
fi

# Wait briefly for the container to start, then discover the assigned port
sleep 2
PORT_LINE=$(podman port "systemd-${SERVICE_NAME}" 8081/tcp 2>/dev/null || true)
PORT=$(echo "$PORT_LINE" | grep -oP ':\K[0-9]+' | head -1)
if [ -z "$PORT" ]; then
    echo "==> Could not determine port. Check: podman port systemd-${SERVICE_NAME}"
    exit 1
fi
echo "==> Listening on port $PORT"
MAX_ATTEMPTS=15
echo "==> Health check: $SERVICE_NAME (port $PORT)..."
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
