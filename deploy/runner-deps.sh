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
# a build sheet (DeckDumpster/ephemeral-ci docs/TEMPLATE.md) that nothing executes and
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

# installable <pkg> -- true when apt can actually install this name.
#
# `apt-cache show` is NOT this test and using it cost a CI run. Ubuntu 24.04's
# 64-bit time_t transition renamed a dozen library packages with a `t64`
# suffix, and it left the OLD name behind in the cache as a record with no
# installation candidate. So `apt-cache show libasound2` succeeds on 24.04
# while `apt-get install libasound2` fails with "has no installation
# candidate" -- and because apt installs a list as one transaction, that single
# unusable name aborted the other ten packages alongside it. Ask apt for the
# candidate version instead, which is the question actually being asked.
installable() {
    local cand
    cand="$(apt-cache policy "$1" 2>/dev/null | sed -n 's/^  Candidate: //p')"
    [ -n "$cand" ] && [ "$cand" != "(none)" ]
}

# WAIT FOR THE DPKG LOCK RATHER THAN FAILING ON IT. A per-run VM boots,
# systemd starts unattended-upgrades, and this script starts installing -- in
# that order, within seconds of each other. Whoever reaches
# /var/lib/dpkg/lock-frontend second gets "Could not get lock ... held by
# process N (unattended-upgr)" and, without this, simply gives up at once.
# It is a RACE, so it fails perhaps one run in several and looks like a broken
# dependency list rather than a timing bug -- the same list had installed
# cleanly on the runs either side of it.
#
# Unquoted on purpose below: it must expand to two words, or to nothing on an
# apt too old to know the option (added in apt 1.9.11).
#
# This is the belt. The braces is unattended-upgrades masked in the Proxmox VM
# template via DeckDumpster/ephemeral-ci scripts/template-substrate.sh, which
# is the durable fix -- a VM that lives thirty minutes has nothing to gain from
# an unattended upgrade. Both, because the template may be rebuilt by someone
# who skips that script.
APT_LOCK_WAIT="-o DPkg::Lock::Timeout=600"

# apt_install <pkg>... -- installs only the packages not already installed,
# mapping each name to the one this release actually carries.
APT_UPDATED=0
# WAIT FOR THE DPKG LOCK RATHER THAN FAILING ON IT.
#
# A per-run VM boots, systemd starts unattended-upgrades, and this script starts
# installing -- in that order, within seconds of each other. Whoever reaches
# /var/lib/dpkg/lock-frontend second gets "Could not get lock ... held by
# process N (unattended-upgr)" and, without this, simply gives up: every
# apt_install call reports "could not install X" and the job dies before
# deploy/ci.sh is reached. It is a RACE, so it fails perhaps one run in several
# and looks like a broken dependency list rather than a timing bug.
#
# apt has had a lock timeout since 1.9.11; this is the whole fix, and it beats a
# retry loop because it waits on the lock itself rather than sleeping and racing
# again. Unquoted on purpose: it must expand to two words, or to nothing on an
# apt too old to know the option.
#
# Ported from pokedumpster's copy of this script, which has carried it since the
# ephemeral runners went in. The durable half is the template, which masks
# unattended-upgrades outright -- but this script also runs on developer
# machines, so it holds the lock-wait half and never disables anyone's updates.
APT_LOCK_WAIT="-o DPkg::Lock::Timeout=600"
apt_install() {
    local want=() p
    for p in "$@"; do
        dpkg -s "$p" >/dev/null 2>&1 && continue
        dpkg -s "${p}t64" >/dev/null 2>&1 && continue
        if installable "$p"; then
            want+=("$p")
        elif installable "${p}t64"; then
            want+=("${p}t64")
        else
            note "no installable package named $p or ${p}t64 on this release -- skipping"
        fi
    done
    [ ${#want[@]} -gt 0 ] || return 0
    [ -n "$SUDO" ] || { printf 'runner-deps: need root to install: %s\n' "${want[*]}" >&2; return 1; }
    if [ "$APT_UPDATED" = 0 ]; then
        # shellcheck disable=SC2086
        $SUDO apt-get update -qq $APT_LOCK_WAIT || true
        APT_UPDATED=1
    fi
    note "installing ${want[*]}"
    # shellcheck disable=SC2086
    if DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq $APT_LOCK_WAIT "${want[@]}"; then
        return 0
    fi
    # One unusable name must not take the rest of the list with it. apt installs
    # a list atomically, so retry singly and let the caller's re-check decide
    # whether what remains is fatal.
    note "batch install failed -- retrying individually"
    for p in "${want[@]}"; do
        # shellcheck disable=SC2086
        DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq $APT_LOCK_WAIT "$p" \
            || note "could not install $p"
    done
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
    note "container engine $v"
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

# OpenCV's shared libraries, needed on the HOST and not only in the image.
#
# The Containerfile installs `libgl1 libglib2.0-0` so the application can import
# cv2 inside the container. The test suite imports cv2 too -- tests/test_ocr.py
# pulls in rapidocr, which pulls in cv2 -- and pytest runs in the venv on the
# host, where nothing had ever installed them. On the old runner they happened to
# be present as a dependency of something else:
#
#   E   ImportError: libGL.so.1: cannot open shared object file
#
# raised during COLLECTION, so it aborts the whole unit tier rather than failing
# one test (de-323).
CV_LIBS=(libgl1 libglib2.0-0)

# Checked by soname through the dynamic linker's cache rather than by package
# name, because the thing that fails is a dlopen: what matters is whether the
# loader can find the object, not whether some package that usually provides it
# is marked installed. ldconfig is in /sbin, which is not on a non-root PATH.
CV_SONAMES=(libGL.so.1 libglib-2.0.so.0)

check_cv_libs() {
    local ldc="" so missing=()
    for ldc in /sbin/ldconfig /usr/sbin/ldconfig ldconfig; do
        command -v "$ldc" >/dev/null 2>&1 && break
        ldc=""
    done
    [ -n "$ldc" ] || { note "no ldconfig found -- cannot verify OpenCV libraries"; return 0; }
    for so in "${CV_SONAMES[@]}"; do
        "$ldc" -p 2>/dev/null | grep -q "	${so} " || missing+=("$so")
    done
    [ ${#missing[@]} -eq 0 ] && return 0
    lack "OpenCV libraries (${missing[*]})" "tests/test_ocr.py imports cv2 via rapidocr on the host; a missing one aborts collection for the whole unit tier"
    return 1
}

run_checks() {
    MISSING=()
    check_podman;        check_uv
    check_subid;         check_linger
    check_chromium_libs; check_cv_libs
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
apt_install "${CV_LIBS[@]}"

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
