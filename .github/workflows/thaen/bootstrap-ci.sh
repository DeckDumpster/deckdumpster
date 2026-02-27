#!/usr/bin/env bash
set -euo pipefail

# Bootstrap the CI host (thaen) from scratch.
#
# Prerequisites:
#   - macOS with Podman installed and a machine running
#   - gh CLI authenticated
#   - ANTHROPIC_API_KEY in environment or ~/.config/mtgc/default.env
#
# Usage: bash .github/workflows/thaen/bootstrap-ci.sh
#
# What it does:
#   1. Creates /opt/dd-ci-{code,data,claude} on macOS host
#   2. Installs Node.js on the Podman VM (rpm-ostree)
#   3. Clones the repo into the VM
#   4. Builds the container image
#   5. Installs Python deps (dev + non-dev)
#   6. Installs Claude CLI on the VM
#   7. Initializes card data (mtg setup --demo)
#   8. Installs daily cron for deps sync
#
# Idempotent — safe to re-run. Skips steps already completed.

REPO_URL="https://github.com/DeckDumpster/deckdumpster.git"
IMAGE="dd-ci-server"
CONTAINERFILE=".github/containers/thaen/ci-server.containerfile"

# macOS host paths (map to /var/opt/* inside VM via virtiofs)
HOST_CODE="/opt/dd-ci-code"
HOST_DATA="/opt/dd-ci-data"
HOST_CLAUDE="/opt/dd-ci-claude"

# VM paths
VM_CODE="/var/opt/dd-ci-code"
VM_DATA="/var/opt/dd-ci-data"
VM_CLAUDE="/var/opt/dd-ci-claude"

info()  { echo "==> $*"; }
skip()  { echo "    (already done, skipping)"; }

# ---------- 1. macOS host directories ----------
info "Creating host directories"
for dir in "$HOST_CODE" "$HOST_DATA" "$HOST_CLAUDE"; do
    if [ -d "$dir" ]; then
        skip
    else
        sudo mkdir -p "$dir"
        sudo chown "$(whoami)" "$dir"
    fi
done

# ---------- 2. Node.js on Podman VM ----------
info "Checking Node.js on Podman VM"
if podman machine ssh -- "which node" &>/dev/null; then
    skip
else
    info "Installing Node.js via rpm-ostree (requires VM reboot)"
    podman machine ssh -- "sudo rpm-ostree install nodejs"
    info "Restarting Podman VM..."
    podman machine stop && podman machine start
fi

# ---------- 3. Clone repo into VM ----------
info "Checking repo clone in VM"
if podman machine ssh -- "test -d ${VM_CODE}/.git" 2>/dev/null; then
    info "Pulling latest"
    podman machine ssh -- "cd ${VM_CODE} && git pull"
else
    info "Cloning repo"
    podman machine ssh -- "git clone ${REPO_URL} ${VM_CODE}"
fi

# ---------- 4. Build container image ----------
info "Building container image"
podman build -t "$IMAGE" -f "$CONTAINERFILE" .

# ---------- 5. Python deps ----------
info "Installing Python dependencies (non-dev + dev)"
podman run --rm -v "${VM_CODE}:/app" --entrypoint bash \
    "$IMAGE" -c "cd /app && uv sync --group dev"

# ---------- 6. Claude CLI ----------
info "Checking Claude CLI on VM"
if podman machine ssh -- "test -x ${VM_CLAUDE}/bin/claude" 2>/dev/null; then
    skip
else
    info "Installing Claude CLI"
    podman machine ssh -- "npm install -g @anthropic-ai/claude-code --prefix ${VM_CLAUDE}"
fi

# ---------- 7. Card data ----------
info "Checking card data"
if podman machine ssh -- "test -f ${VM_DATA}/collection.sqlite" 2>/dev/null; then
    skip
else
    info "Initializing card data (mtg setup --demo) — this takes a few minutes"
    podman machine ssh -- "mkdir -p ${VM_DATA}"
    podman run --rm \
        -v "${VM_CODE}:/app" \
        -v "${VM_DATA}:/data" \
        -e MTGC_HOME=/data \
        --entrypoint /app/.venv/bin/python3 \
        "$IMAGE" /app/.venv/bin/mtg setup --demo
fi

# ---------- 8. Daily cron ----------
CRON_CMD="podman run --rm -v ${VM_CODE}:/app --entrypoint bash ${IMAGE} -c 'cd /app && git pull && uv sync --group dev'"
info "Checking daily cron job"
if crontab -l 2>/dev/null | grep -qF "dd-ci-code"; then
    skip
else
    info "Installing daily cron (05:00 — deps sync)"
    (crontab -l 2>/dev/null; echo "0 5 * * * ${CRON_CMD} # dd-ci-code daily sync") | crontab -
fi

echo ""
info "Bootstrap complete. Test with:"
echo "    GH_TOKEN=\$(gh auth token) bash .github/ci/thaen/preflight.sh <issue> DeckDumpster/deckdumpster thaen ready_for_claude_plan"
echo "    ANTHROPIC_API_KEY=... GH_TOKEN=\$(gh auth token) bash .github/ci/thaen/sandbox-run.sh plan <issue> DeckDumpster/deckdumpster"
