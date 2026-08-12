#!/usr/bin/env bash
#
# Gate: bringing up a --test instance must write nothing to Podman's DEFAULT
# store (de-3a0).
#
# de-3mo gave non-prod container storage somewhere else to live
# (MTGC_STORE_ROOT, deploy/store-lib.sh). Nothing checked that it works end to
# end, and that is the whole problem: / has hit 100% from non-prod container
# bytes twice, and every fix so far has been a convention — set this variable,
# remember that flag — which is another way of saying nobody would notice the
# day it stopped holding. A rule nobody tests is not enforced. So this drives a
# real `deploy/setup.sh <name> --test`, with a real image build, and measures
# where the bytes actually went.
#
# WHAT IT ASSERTS, and why it is four things rather than one
#
#   1. NEGATIVE, exact.  The default store holds no mtgc:<instance> image and no
#      mtgc-<instance>-data volume afterwards.
#   2. NEGATIVE, bulk.   $HOME/.local/share/containers grew by no more than
#      MTGC_STORE_GATE_TOLERANCE_KB (see "The tolerance" below).
#   3. POSITIVE, exact.  The probe store holds both, and the generated Quadlet
#      names that store in GlobalArgs=.
#   4. POSITIVE, bulk.   The probe store is at least
#      MTGC_STORE_GATE_FLOOR_KB — an image build's worth of bytes landed
#      SOMEWHERE.
#
# The positives are not decoration. A gate that only checks the negative passes
# just as happily when setup.sh did nothing at all — a build that failed and got
# swallowed, a shim that sent every call to a store nobody looked in. Both
# halves, or the whole thing can go green on a machine that never built
# anything.
#
# Exact and bulk are two instruments because each covers the other's blind spot.
# `podman image exists` is precise and immune to prod writing to its own volume
# while we measure, but it only knows about the two names we ask for; a build
# that spilled three gigabytes of blobs into the default store's cache would not
# register. `du` sees any byte at all, but it is a moving target on a box where
# prod is live, and it undercounts subuid-owned layer directories it cannot
# read. Neither is sufficient. Together they are hard to fool.
#
# Finally it tears the instance and the probe store down and re-checks, because
# a gate that fills a disk every run is its own version of the bug.
#
# THE TOLERANCE is not zero, and that is measured rather than conceded. Even
# with --root and --runroot set, podman keeps a few things at user scope:
# containers/image writes its blob-info cache to
# $XDG_DATA_HOME/containers/cache/blob-info-cache-v1.boltdb, and
# $HOME/.config/containers is config that has nothing to do with the store. That
# is kilobytes. The default is set well above what was observed and far below
# an image layer, so the gate has room for podman's bookkeeping and none at all
# for a leaked build. Assertion 1 is what keeps this from being slack.
#
# WHERE THE PROBE STORE GOES
#
#   MTGC_STORE_GATE_ROOT      explicit, wins
#   <configured store>.gate   a sibling of the box's non-prod store, so the
#                             gate's bytes land on the disk that was chosen for
#                             exactly this kind of traffic. Not the store
#                             itself: a warm store would make assertion 4
#                             meaningless and the teardown would delete real
#                             instances' images.
#   $TMPDIR/mtgc-store-gate-$$   last resort, with a warning if it turns out to
#                             share a filesystem with $HOME
#
# It is never Podman's default store, and refuses to run if it resolves inside
# one — that is the store under test.
#
# INHERITED ACTIVATION. .github/workflows/ci.yml activates the box's store for
# the whole job when one is configured, so this script may start with the shim
# on PATH. It deactivates first: "the default store" has to mean Podman's, or
# the measurements are of the wrong directory and the gate passes vacuously.
#
# Usage:
#   bash deploy/store-isolation-gate.sh [instance]
#
# Run by .github/workflows/ci.yml on every PR. Takes as long as an image build.
#
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

INSTANCE="${1:-store-gate}"
if [ "$INSTANCE" = "prod" ]; then
    echo "ERROR: this gate builds and then destroys an instance. Not prod." >&2
    exit 1
fi

# 64 MiB. Observed growth on the deployment box was ~0; see "The tolerance".
TOLERANCE_KB="${MTGC_STORE_GATE_TOLERANCE_KB:-65536}"
# 256 MiB. The image alone is over a gigabyte, so this only has to be large
# enough that an empty store cannot clear it.
FLOOR_KB="${MTGC_STORE_GATE_FLOOR_KB:-262144}"

DEFAULT_STORE="${HOME}/.local/share/containers"
QUADLET_FILE="${HOME}/.config/containers/systemd/mtgc-${INSTANCE}.container"
STORE_ENV="${HOME}/.config/mtgc/store.env"

# --- Where the probe store goes -------------------------------------------

# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"

mtgc_store_load_config
CONFIGURED_STORE="${MTGC_STORE_ROOT:-}"

# From here on, bare `podman` must mean Podman's default store: that is the one
# under test, and CI may have activated another one for the whole job.
mtgc_store_deactivate

if [ -n "${MTGC_STORE_GATE_ROOT:-}" ]; then
    PROBE="${MTGC_STORE_GATE_ROOT%/}"
elif [ -n "$CONFIGURED_STORE" ]; then
    PROBE="${CONFIGURED_STORE%/}.gate"
else
    PROBE="${TMPDIR:-/tmp}/mtgc-store-gate-$$"
fi

# The probe store is a throwaway this script creates and then `rm -rf`s, so the
# path it resolved to is checked before anything is written to it, not after.
refuse() {
    echo "ERROR: bad probe store: $PROBE" >&2
    echo "       $*" >&2
    echo "       Set MTGC_STORE_GATE_ROOT to a directory of its own." >&2
    exit 1
}

# Absolute, no shell metacharacters, not "/" — the same rules store-lib.sh
# applies to a real store root, since this is about to become one.
mtgc_store_validate "$PROBE" || exit 1

case "$PROBE" in
    "$DEFAULT_STORE"|"$DEFAULT_STORE"/*)
        refuse "that is inside Podman's default store — the store under test." ;;
esac
case "$HOME" in
    "$PROBE"|"$PROBE"/*)
        refuse "\$HOME is inside it, and this script deletes it afterwards." ;;
esac
if [ -n "$CONFIGURED_STORE" ] && [ "$PROBE" = "${CONFIGURED_STORE%/}" ]; then
    refuse "that is the box's real non-prod store. Tearing it down would take
       every instance living in it with it, and a warm store would make the
       positive assertions below meaningless."
fi

fs_of() {
    df --output=source "$1" 2>/dev/null | tail -1 || true
}

DEFAULT_FS="$(fs_of "$DEFAULT_STORE")"
PROBE_FS="$(fs_of "$(dirname "$PROBE")")"

echo "==> Container-store isolation gate"
echo "    Instance:      $INSTANCE"
echo "    Default store: $DEFAULT_STORE   (${DEFAULT_FS:-unknown})"
echo "    Probe store:   $PROBE   (${PROBE_FS:-unknown})"
if [ -n "$DEFAULT_FS" ] && [ "$DEFAULT_FS" = "$PROBE_FS" ]; then
    echo "    NOTE: both are on one filesystem, so this run proves the stores are"
    echo "          separate DIRECTORIES but not that they are separate DISKS."
    echo "          Name the box's non-prod disk in ~/.config/mtgc/store.env."
fi

# --- Measurement -----------------------------------------------------------

# A rootless layer store always has a handful of subuid-owned directories `du`
# cannot descend into. It prints the total anyway and then exits non-zero, which
# under `set -o pipefail` would kill the gate on its first measurement — so the
# status is dropped and the number kept. The directories are stable, so the
# delta stays meaningful, and assertion 1 is what covers the undercount.
size_kb() {
    local kb=""
    if [ -d "$1" ]; then
        kb="$(du -sk "$1" 2>/dev/null | cut -f1 || true)"
    fi
    echo "${kb:-0}"
}

# `podman` with no store flags, deliberately: this is the default store.
default_store_has() {
    podman "$1" exists "$2" >/dev/null 2>&1
}

# The instance's own Quadlet is where its store is recorded, so the probe store
# is queried the same way teardown.sh finds it — through the unit, not through a
# variable this script happens to be holding.
probe_store_has() {
    local args
    args="$(sed -n 's/^GlobalArgs=//p' "$QUADLET_FILE" | head -n1)"
    [ -n "$args" ] || return 1
    # shellcheck disable=SC2086  # the store root is charset-validated by store-lib.sh
    podman $args "$1" exists "$2" >/dev/null 2>&1
}

IMAGE="mtgc:${INSTANCE}"
VOLUME="mtgc-${INSTANCE}-data"

# --- Teardown, which must also run when an assertion fails ------------------

STORE_ENV_WAS_THERE=true
[ -f "$STORE_ENV" ] || STORE_ENV_WAS_THERE=false

cleanup() {
    echo "==> Cleaning up"
    bash "$REPO_DIR/deploy/teardown.sh" "$INSTANCE" --purge >/dev/null 2>&1 || true
    MTGC_STORE_ROOT="$PROBE" bash "$REPO_DIR/deploy/store-teardown.sh" >/dev/null 2>&1 || true
    rm -rf "$PROBE"
    # setup.sh scaffolds this commented-out on a box that has none. Harmless,
    # but "leave nothing behind" means nothing.
    [ "$STORE_ENV_WAS_THERE" = true ] || rm -f "$STORE_ENV"
}
trap cleanup EXIT

# A previous run that died mid-flight leaves an instance behind, and its image
# would then be a pre-existing byte the measurement blames on this run.
bash "$REPO_DIR/deploy/teardown.sh" "$INSTANCE" --purge >/dev/null 2>&1 || true

BEFORE_KB="$(size_kb "$DEFAULT_STORE")"
echo "    Default store before: ${BEFORE_KB} KB"

# --- The thing being gated --------------------------------------------------

echo "==> MTGC_STORE_ROOT=$PROBE bash deploy/setup.sh $INSTANCE --test"
MTGC_STORE_ROOT="$PROBE" bash "$REPO_DIR/deploy/setup.sh" "$INSTANCE" --test

AFTER_KB="$(size_kb "$DEFAULT_STORE")"
PROBE_KB="$(size_kb "$PROBE")"
GREW_KB=$((AFTER_KB - BEFORE_KB))

echo ""
echo "==> Results"
echo "    Default store: ${BEFORE_KB} -> ${AFTER_KB} KB  (${GREW_KB} KB, tolerance ${TOLERANCE_KB})"
echo "    Probe store:   ${PROBE_KB} KB  (floor ${FLOOR_KB})"

FAILED=false
fail() {
    echo "FAIL: $*" >&2
    FAILED=true
}

# 1. NEGATIVE, exact.
if default_store_has image "$IMAGE"; then
    fail "$IMAGE is in Podman's default store — the disk prod runs from."
fi
if default_store_has volume "$VOLUME"; then
    fail "$VOLUME is in Podman's default store — the disk prod runs from."
fi

# 2. NEGATIVE, bulk.
if [ "$GREW_KB" -gt "$TOLERANCE_KB" ]; then
    fail "$DEFAULT_STORE grew by ${GREW_KB} KB, over the ${TOLERANCE_KB} KB tolerance."
fi

# 3. POSITIVE, exact. Without these the gate would pass over a setup.sh that
#    quietly built nothing.
if ! grep -q "^GlobalArgs=.*--root=${PROBE}/storage" "$QUADLET_FILE" 2>/dev/null; then
    fail "the generated Quadlet does not name the probe store. systemd would" \
         "start this instance out of the default store."
fi
if ! probe_store_has image "$IMAGE"; then
    fail "$IMAGE is not in the probe store either — nothing was built."
fi
if ! probe_store_has volume "$VOLUME"; then
    fail "$VOLUME is not in the probe store either — no data volume was created."
fi

# 4. POSITIVE, bulk.
if [ "$PROBE_KB" -lt "$FLOOR_KB" ]; then
    fail "the probe store holds only ${PROBE_KB} KB, under the ${FLOOR_KB} KB floor." \
         "An image build did not happen."
fi

if [ "$FAILED" = true ]; then
    echo ""
    echo "Non-prod container bytes are landing on the disk prod runs from, or"
    echo "the bring-up they were supposed to come from did not happen."
    echo "See deploy/store-lib.sh and deploy/README.md -> Container storage."
    exit 1
fi

# --- ...and leave nothing behind -------------------------------------------

cleanup
trap - EXIT

FINAL_KB="$(size_kb "$DEFAULT_STORE")"
LEFT_KB=$((FINAL_KB - BEFORE_KB))
echo "    Default store after cleanup: ${FINAL_KB} KB  (${LEFT_KB} KB vs baseline)"

if [ "$LEFT_KB" -gt "$TOLERANCE_KB" ]; then
    echo "FAIL: teardown left ${LEFT_KB} KB behind in $DEFAULT_STORE." >&2
    exit 1
fi
if [ -e "$PROBE" ]; then
    echo "FAIL: the probe store is still on disk: $PROBE" >&2
    exit 1
fi
if [ -f "$QUADLET_FILE" ]; then
    echo "FAIL: teardown left the Quadlet behind: $QUADLET_FILE" >&2
    exit 1
fi

echo ""
echo "==> PASS — a --test bring-up wrote nothing to Podman's default store."
