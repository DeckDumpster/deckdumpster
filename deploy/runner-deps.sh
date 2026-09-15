#!/usr/bin/env bash
#
# The system dependencies deploy/ci.sh needs, as a script rather than a
# paragraph.
#
#   bash deploy/runner-deps.sh            install anything missing (idempotent)
#   bash deploy/runner-deps.sh --check    report what is missing; exit 1 if any
#
# WHY THIS EXISTS. deploy/ci.sh calls podman and uv and has never installed
# either. It passed for a year because the one runner it ever ran on had them
# installed by hand, so the dependency was real but unmodelled -- it lived in
# a build sheet (deploy/ephemeral-runner/TEMPLATE.md) that nothing executes and
# nothing checks. The first runner built from that sheet by a different route
# failed with `exit code 127` and no name: not "podman is missing", just a
# number, three steps into a job, on a VM that was destroyed forty seconds
# later. A dependency a human has to remember is a dependency that is missing
# on the next machine.
#
# So this file is the list, it is executable, and ci.sh refuses to start until
# --check passes. Adding a tool to ci.sh means adding it here.
#
# IDEMPOTENT BY CONSTRUCTION. Every action checks for its own outcome first, so
# the fast path on an already-provisioned box is a handful of `command -v`
# calls and no package manager at all. It is safe to run at the head of every
# CI job; on the long-lived runner it costs about a second.
#
# NOT RUN AUTOMATICALLY BY ci.sh. Installing packages needs sudo, and a test
# script that silently apt-installs on a developer's laptop is a worse problem
# than the one it solves. ci.sh only *checks*; the caller installs.
set -uo pipefail

MODE=install
case "${1:-}" in
    --check) MODE=check ;;
    "")      MODE=install ;;
    *)       printf 'usage: runner-deps.sh [--check]\n' >&2; exit 2 ;;
esac

MISSING=()
note()  { printf 'runner-deps: %s\n' "$*"; }
lack()  { MISSING+=("$1"); printf 'runner-deps: MISSING %s -- %s\n' "$1" "$2" >&2; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        SUDO="sudo -n"
    fi
fi

# apt_install <pkg>... -- installs only the packages not already installed.
# Ubuntu 24.04 renamed several library packages with a `t64` suffix (the 64-bit
# time_t transition), so a name that exists on 22.04 is absent on 24.04 and
# vice versa. Resolve each name against the actual package cache and skip one
# that this release does not have, rather than failing the whole transaction on
# a single renamed library.
APT_UPDATED=0
apt_install() {
    local want=() p
    for p in "$@"; do
        dpkg -s "$p" >/dev/null 2>&1 && continue
        if apt-cache show "$p" >/dev/null 2>&1; then
            want+=("$p")
        elif apt-cache show "${p}t64" >/dev/null 2>&1; then
            want+=("${p}t64")
        else
            note "no package named $p or ${p}t64 on this release -- skipping"
        fi
    done
    [ ${#want[@]} -gt 0 ] || return 0
    [ -n "$SUDO" ] || { printf 'runner-deps: need root to install: %s\n' "${want[*]}" >&2; return 1; }
    if [ "$APT_UPDATED" = 0 ]; then
        $SUDO apt-get update -qq || true
        APT_UPDATED=1
    fi
    note "installing ${want[*]}"
    DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq "${want[@]}"
}

# ---------------------------------------------------------------------------
# Podman, rootless-capable.
#
# uidmap        newuidmap/newgidmap; without it `podman run` fails with
#               "newuidmap not found".
# slirp4netns   rootless networking. Podman 4.x prefers pasta when present;
#               either works, and slirp4netns is in the default repos.
# fuse-overlayfs  rootless overlay storage. Without it podman falls back to
#               vfs, where the builder stage takes minutes instead of seconds.
# ---------------------------------------------------------------------------
PODMAN_MIN_MAJOR=4
PODMAN_MIN_MINOR=4

check_podman() {
    command -v podman >/dev/null 2>&1 || { lack podman "deploy/ci.sh calls 'podman image prune' and 'podman port'"; return 1; }
    local v major minor
    v="$(podman --version 2>/dev/null | awk '{print $3}')"
    major="${v%%.*}"; minor="${v#*.}"; minor="${minor%%.*}"
    case "${major:-x}${minor:-x}" in *[!0-9]*) note "cannot parse podman version [$v] -- not enforcing the floor"; return 0 ;; esac
    if [ "$major" -lt "$PODMAN_MIN_MAJOR" ] || { [ "$major" -eq "$PODMAN_MIN_MAJOR" ] && [ "$minor" -lt "$PODMAN_MIN_MINOR" ]; }; then
        # Not a missing binary -- a silently wrong one. Quadlet .container
        # support arrived in 4.4; older podman IGNORES .container files, so
        # `systemctl --user start mtgc-<instance>` succeeds having started
        # nothing and every later `podman port` returns empty.
        lack "podman>=${PODMAN_MIN_MAJOR}.${PODMAN_MIN_MINOR}" \
             "found $v; Quadlet .container files are ignored below ${PODMAN_MIN_MAJOR}.${PODMAN_MIN_MINOR} and CI fails far downstream with an empty port"
        return 1
    fi
    note "podman $v"
}

check_uv() {
    if command -v uv >/dev/null 2>&1; then
        note "uv $(uv --version 2>/dev/null | awk '{print $2}')"
        return 0
    fi
    # uv installs to ~/.local/bin, which a non-login shell may not have on PATH.
    if [ -x "$HOME/.local/bin/uv" ]; then
        note "uv present at ~/.local/bin/uv but not on PATH"
        export PATH="$HOME/.local/bin:$PATH"
        return 0
    fi
    lack uv "deploy/ci.sh calls 'uv sync' and 'uv run pytest'"
    return 1
}

check_subid() {
    local u; u="$(id -un)"
    grep -q "^${u}:" /etc/subuid 2>/dev/null && grep -q "^${u}:" /etc/subgid 2>/dev/null && return 0
    lack "subuid/subgid for ${u}" "rootless podman cannot map users without them"
    return 1
}

check_linger() {
    command -v loginctl >/dev/null 2>&1 || return 0
    local u; u="$(id -un)"
    [ "$(loginctl show-user "$u" -p Linger --value 2>/dev/null)" = "yes" ] && return 0
    # deploy/setup.sh writes Quadlet units under ~/.config/containers/systemd,
    # which systemd only reads inside a live user session. Without lingering the
    # failure surfaces as a systemctl --user error that says nothing about
    # lingering.
    lack "linger for ${u}" "systemctl --user has no user manager to talk to; Quadlet units are never generated"
    return 1
}

# Chromium's shared libraries. `uv run shot-scraper install` downloads the
# Chromium binary and none of its system dependencies.
CHROMIUM_LIBS=(libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2
               libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2
               libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0)

check_chromium_libs() {
    command -v dpkg >/dev/null 2>&1 || return 0
    local p missing=()
    for p in "${CHROMIUM_LIBS[@]}"; do
        dpkg -s "$p" >/dev/null 2>&1 && continue
        dpkg -s "${p}t64" >/dev/null 2>&1 && continue
        missing+=("$p")
    done
    [ ${#missing[@]} -eq 0 ] && return 0
    lack "chromium libraries (${missing[*]})" "the UI tier launches headless Chromium via shot-scraper"
    return 1
}

run_checks() {
    MISSING=()
    check_podman;        check_uv
    check_subid;         check_linger
    check_chromium_libs
}

if [ "$MODE" = check ]; then
    run_checks
    if [ ${#MISSING[@]} -gt 0 ]; then
        printf '\nrunner-deps: %d dependency group(s) missing on %s.\n' "${#MISSING[@]}" "$(hostname)" >&2
        printf 'runner-deps: install them with:  sudo bash deploy/runner-deps.sh\n' >&2
        exit 1
    fi
    note "all dependencies present"
    exit 0
fi

# --------------------------------- install ---------------------------------
note "installing dependencies for $(id -un) on $(hostname)"

command -v podman >/dev/null 2>&1 || apt_install podman uidmap slirp4netns fuse-overlayfs
apt_install "${CHROMIUM_LIBS[@]}"

if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
    note "installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

RUNUSER="$(id -un)"
if ! grep -q "^${RUNUSER}:" /etc/subuid 2>/dev/null || ! grep -q "^${RUNUSER}:" /etc/subgid 2>/dev/null; then
    note "adding subuid/subgid range for ${RUNUSER}"
    $SUDO usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$RUNUSER" || true
fi

if command -v loginctl >/dev/null 2>&1 \
   && [ "$(loginctl show-user "$RUNUSER" -p Linger --value 2>/dev/null)" != "yes" ]; then
    note "enabling linger for ${RUNUSER}"
    $SUDO loginctl enable-linger "$RUNUSER" || true
fi

# Re-check and report. The installer exits non-zero when something it tried to
# install is still absent, so a partial install is a failure here rather than a
# surprise inside ci.sh.
printf '\n'
run_checks
if [ ${#MISSING[@]} -gt 0 ]; then
    printf '\nrunner-deps: still missing after install: %s\n' "${MISSING[*]}" >&2
    exit 1
fi
note "all dependencies present"
