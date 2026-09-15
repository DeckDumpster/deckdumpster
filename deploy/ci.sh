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

# Before anything else: are the tools this script calls actually here?
#
# podman and uv are called below and installed by neither this script nor the
# repository. That held for as long as CI only ever ran on one hand-built box.
# The first runner built by another route died at `exit code 127` -- a number,
# with no name attached, three steps in, on a VM that no longer existed by the
# time anyone read the log. deploy/runner-deps.sh is now the list, and this
# names what is missing before any of it runs (de-323).
#
# It checks; it does not install. Installing needs sudo, and a test script that
# quietly apt-installs on someone's laptop is worse than the gap it closes.
echo "==> Runner dependencies"
bash deploy/runner-deps.sh --check

# Before the job writes several gigabytes: is there room? A run that fills the
# disk does not fail as a disk error -- at 697M free a cargo link reported
# `ld terminated with signal 7 [Bus error]`, which reads as a broken
# toolchain. This runs after the store is selected, so it measures the disk
# the build will actually write to (de-yef).
echo "==> Disk floor"
bash deploy/diskcheck.sh --floor "${MTGC_STORE_ROOT:-$HOME}"

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

echo "==> Ephemeral runner script tests"
bash deploy/ephemeral-runner/test-teardown.sh

echo "==> Install dependencies"
uv sync

echo "==> Install Playwright browser"
uv run shot-scraper install

echo "==> Build and start test container"
bash deploy/setup.sh "$INSTANCE" --test

# THIS FUNCTION MUST EXPLAIN ITSELF WHEN IT GIVES UP.
#
# It used to print exactly `Server failed to start` and return 1 -- no port, no
# curl exit code, no container state, no logs. On the long-lived runner that was
# merely annoying, because the box was still there to poke at afterwards. On an
# ephemeral runner the VM is destroyed seconds later, so that one line was the
# entire record of the failure and there was no way to tell a container that had
# not been created from one that was crash-looping from one that was simply slow.
#
# So the last attempt records WHY it failed, and the give-up path dumps the state
# a person would have gone looking for. The timeout is deliberately unchanged:
# raising it would be guessing at "slow" before knowing that slow is the problem
# at all (de-323).
WAIT_TRIES="${MTGC_WAIT_TRIES:-20}"
WAIT_SLEEP="${MTGC_WAIT_SLEEP:-3}"

wait_for_server() {
    local i port curl_rc=0 port_err=""
    for i in $(seq 1 "$WAIT_TRIES"); do
        port_err="$(podman port "systemd-mtgc-${INSTANCE}" 8081/tcp 2>&1)" || port_err="${port_err}"
        port="$(printf '%s' "$port_err" | head -1 | cut -d: -f2)"
        case "$port" in ''|*[!0-9]*) port="" ;; esac
        if [ -n "$port" ]; then
            curl -skf "https://localhost:${port}/" >/dev/null 2>&1 && return 0
            curl_rc=$?
        fi
        sleep "$WAIT_SLEEP"
    done

    {
        printf '\nServer failed to start after %ss.\n\n' "$(( WAIT_TRIES * WAIT_SLEEP ))"
        printf -- '--- podman port systemd-mtgc-%s 8081/tcp ---\n%s\n' "$INSTANCE" "${port_err:-<no output>}"
        printf -- '--- resolved port: %s ---\n' "${port:-<none>}"
        if [ -n "$port" ]; then
            printf -- '--- last curl exit: %s ---\n' "$curl_rc"
            # curl 35 is an SSL CONNECT error: the TCP connection succeeded and
            # the TLS handshake did not. The exit code alone cannot separate a
            # protocol/cipher refusal from a reset, so ask for the handshake
            # itself. -k is already in use, so this is never about trust.
            printf -- '\n--- curl -kv https://localhost:%s/ ---\n' "$port"
            curl -kv --max-time 10 "https://localhost:${port}/" 2>&1 | tail -30
            printf -- '\n--- openssl s_client -connect localhost:%s ---\n' "$port"
            openssl s_client -connect "localhost:${port}" </dev/null 2>&1 | head -30
            printf -- '\n--- local openssl ---\n'
            openssl version 2>&1
            printf -- '\n--- plain TCP reachable? ---\n'
            timeout 5 bash -c "</dev/tcp/127.0.0.1/${port}" 2>&1 \
                && echo "TCP connect to 127.0.0.1:${port} OK" \
                || echo "TCP connect to 127.0.0.1:${port} FAILED"
        fi
        printf -- '\n--- podman ps -a ---\n'
        podman ps -a 2>&1 | head -20
        printf -- '\n--- systemctl --user status mtgc-%s ---\n' "$INSTANCE"
        systemctl --user status "mtgc-${INSTANCE}" --no-pager 2>&1 | head -25
        printf -- '\n--- journalctl --user -u mtgc-%s (last 60) ---\n' "$INSTANCE"
        journalctl --user -u "mtgc-${INSTANCE}" -n 60 --no-pager 2>&1 | tail -60
        printf -- '\n--- container logs (last 60) ---\n'
        podman logs --tail 60 "systemd-mtgc-${INSTANCE}" 2>&1 | tail -60
    } >&2
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
