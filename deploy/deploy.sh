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
    # Remember exactly what we built, so the verification below can prove the
    # RUNNING container is this image and not an older one that happened to
    # survive. store-lib.sh's own header warns about a deploy tagging into one
    # store while systemd serves another; on 2026-08-30 a worse version of that
    # untagged mtgc:prod out from under the live unit entirely.
    BUILT_IMAGE_ID="$(podman image inspect --format '{{.Id}}' "mtgc:${INSTANCE}" 2>/dev/null || true)"
    echo "==> Built image ${BUILT_IMAGE_ID:0:12}"

    echo "==> Reloading systemd (picks up Quadlet changes)..."
    systemctl --user daemon-reload

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
# Wait briefly for the container to start, then discover the assigned port
sleep 2
PORT_LINE=$(podman port "systemd-${SERVICE_NAME}" 8081/tcp 2>/dev/null || true)
PORT=$(echo "$PORT_LINE" | grep -oP ':\K[0-9]+' | head -1)
if [ -z "$PORT" ]; then
    echo "==> Could not determine port. Check: podman port systemd-${SERVICE_NAME}"
    exit 1
fi
echo "==> Listening on port $PORT"
# ── Deployment safety check ──────────────────────────────────────────────────
#
# WHAT THIS ANSWERS, and why the old version did not.
#
# The old check curled `/` once, printed "passed" and exited. On 2026-08-30 it
# passed at 02:11 and the container died at 02:12:33 — 90 seconds later — after
# a store-gate run untagged mtgc:prod out from under the live unit. podman then
# treated the tag as a REGISTRY reference, crash-looped 4195 times, and prod was
# down for 15.5 hours. Nothing looked again, because the deploy had already said
# it was fine.
#
# So the question is not "did it start". It is:
#   1. Is the container serving the image we JUST BUILT, or an older survivor?
#   2. Does it answer through the real entry point?
#   3. Is it STILL doing both once it has settled?
#
# (3) is the one that matters most and is the cheapest to get wrong: a deploy
# that verifies at t+2s and never looks again cannot distinguish "healthy" from
# "about to die". Nothing here touches the CDN — Cloudflare Access makes edge
# caching structurally impossible on this hostname, so a CDN assertion tests a
# property that cannot be violated and only produces noise.
MAX_ATTEMPTS=15

serving() {
    curl -skf --connect-timeout 3 "https://localhost:${PORT}/" >/dev/null 2>&1
}

running_image_id() {
    podman inspect --format '{{.Image}}' "systemd-${SERVICE_NAME}" 2>/dev/null || true
}

echo "==> [1/3] Health check: $SERVICE_NAME (port $PORT)..."
ok=0
for i in $(seq 1 $MAX_ATTEMPTS); do
    if serving; then echo "    answering (attempt $i/$MAX_ATTEMPTS)"; ok=1; break; fi
    echo "    attempt $i/$MAX_ATTEMPTS failed, waiting 2s..."
    sleep 2
done
[ "$ok" = 1 ] || { echo "==> DEPLOY FAILED: never answered on port $PORT"; exit 1; }

echo "==> [2/3] Identity: is the running container the image we just built?"
if [ -n "${BUILT_IMAGE_ID:-}" ]; then
    RUNNING_IMAGE_ID="$(running_image_id)"
    if [ -z "$RUNNING_IMAGE_ID" ]; then
        echo "==> DEPLOY FAILED: no running container named systemd-${SERVICE_NAME}"
        exit 1
    fi
    if [ "$RUNNING_IMAGE_ID" != "$BUILT_IMAGE_ID" ]; then
        echo "==> DEPLOY FAILED: serving ${RUNNING_IMAGE_ID:0:12}, built ${BUILT_IMAGE_ID:0:12}."
        echo "    The restart came up on a DIFFERENT image than this deploy produced —"
        echo "    the deploy would report success while users keep seeing old code."
        exit 1
    fi
    echo "    serving ${RUNNING_IMAGE_ID:0:12}, matches the build"
else
    echo "    skipped (no build in this run — restart-only path)"
fi

# ── [3/3] Settle ────────────────────────────────────────────────────────────
# The 2026-08-30 outage lived entirely in this window. 90s covers it with room;
# override with MTGC_SETTLE_SECONDS=0 for a fast local loop, which is explicit
# rather than silent.
SETTLE="${MTGC_SETTLE_SECONDS:-90}"
if [ "$SETTLE" -gt 0 ]; then
    echo "==> [3/3] Settling ${SETTLE}s, then re-verifying (the 2026-08-30 window)..."
    sleep "$SETTLE"
    if ! serving; then
        echo "==> DEPLOY FAILED: answered at first, then stopped within ${SETTLE}s."
        echo "    This is the 2026-08-30 shape exactly. Check:"
        echo "      systemctl --user status ${SERVICE_NAME}"
        echo "      podman images | grep ${SERVICE_NAME#mtgc-}"
        exit 1
    fi
    if [ -n "${BUILT_IMAGE_ID:-}" ] && [ "$(running_image_id)" != "$BUILT_IMAGE_ID" ]; then
        echo "==> DEPLOY FAILED: the container was replaced during the settle window."
        exit 1
    fi
    echo "    still serving the built image after ${SETTLE}s"
else
    echo "==> [3/3] Settle skipped (MTGC_SETTLE_SECONDS=0)"
fi

echo "==> Deploy verified: serving, correct image, stable."
exit 0
