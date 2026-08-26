#!/usr/bin/env bash
#
# What CI runs (de-xz8).
#
# `.github/workflows/ci.yml` checks out the repo and calls this script. It does
# nothing else, and that is the point: a gate wired in here runs in CI *and* by
# hand, and there is no second list of steps to keep in step with this one.
#
# It used to be a dozen inline `run:` steps, so "what CI runs" was only
# expressible as a YAML file: a red CI could not be reproduced locally, and a
# new gate could only be added by editing the workflow. The rig's agent
# instructions already told people to wire gates into `deploy/ci.sh` -- a file
# that did not exist -- and de-3a0 lost a session to the contradiction before
# wiring its gate in as its own inline step instead.
#
# Run it by hand with an instance name of your own:
#
#   INSTANCE=ci-<yourname> bash deploy/ci.sh
#
# The default is `ci-test`, which is the runner's own instance. On the
# deployment box the self-hosted runner and your worktree share a machine, so
# taking the default while CI is running tears down its container mid-job.
#
# The UI tier drives Claude Vision and needs ANTHROPIC_API_KEY in the
# environment; without it `anthropic.Anthropic()` raises and that tier fails
# loudly rather than skipping. CI passes it in as a repository secret.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

export INSTANCE="${INSTANCE:-ci-test}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"

# Nothing this job builds belongs on the disk prod runs from (de-3mo). Which
# disk that is on the runner box is host config, not a repo constant, so it
# comes from ~/.config/mtgc/store.env; unconfigured, this is a no-op and
# everything uses Podman's default store exactly as before.
#
# Activating it once here is enough because everything below runs in this
# shell's process tree -- including `uv run pytest`, whose conftests shell out
# to `podman port` and `podman exec` and would otherwise look in the default
# store. As separate workflow steps this needed re-exporting through
# GITHUB_PATH/GITHUB_ENV, since Actions runs each step in a fresh shell.
# shellcheck source=deploy/store-lib.sh
. deploy/store-lib.sh
mtgc_store_load_config
mtgc_store_activate

# The old workflow tore the instance down in an `if: always()` step, so a run
# that failed anywhere still cleaned up. A trap is that, and it also covers a
# hand-run interrupted partway.
trap 'bash deploy/teardown.sh "$INSTANCE" --purge >/dev/null 2>&1 || true' EXIT

echo "==> Clean up stale containers and images"
bash deploy/teardown.sh "$INSTANCE" --purge 2>/dev/null || true
podman image prune -f 2>/dev/null || true

# Before the job writes several more gigabytes of its own: a --test bring-up
# must put nothing under $HOME, which on the deployment box is the disk prod
# runs from (de-3a0). de-3mo gave those bytes somewhere else to live, but
# nothing checked that it holds, and a rule nobody tests is not enforced -- /
# has hit 100% from non-prod container bytes twice. Costs one image build; see
# deploy/store-isolation-gate.sh for what it asserts and why the tolerance is
# not zero.
echo "==> Container-store isolation gate"
bash deploy/store-isolation-gate.sh

echo "==> Install dependencies"
uv sync

echo "==> Install Playwright browser"
uv run shot-scraper install

echo "==> Build and start test container"
bash deploy/setup.sh "$INSTANCE" --test

wait_for_server() {
    local i port
    for i in $(seq 1 20); do
        port="$(podman port "systemd-mtgc-${INSTANCE}" 8081/tcp | cut -d: -f2)" || port=""
        if [ -n "$port" ] && curl -skf "https://localhost:${port}/" >/dev/null; then
            return 0
        fi
        sleep 3
    done
    echo "Server failed to start" >&2
    return 1
}

echo "==> Wait for server"
wait_for_server

echo "==> Run unit tests"
uv run pytest tests/ -q --ignore=tests/integration --ignore=tests/ui

echo "==> Run integration tests"
uv run pytest tests/integration/ -q --instance "$INSTANCE"

echo "==> Run UI scenario tests"
uv run pytest tests/ui/ -q --instance "$INSTANCE"
