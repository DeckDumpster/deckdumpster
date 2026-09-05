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
#   1. NEGATIVE, by name.      The default store holds no mtgc:<instance> image,
#      no mtgc-<instance>-data volume and no systemd-mtgc-<instance> container
#      afterwards.
#   2. NEGATIVE, by identity.  No image carrying the Containerfile's build label
#      arrived in the default store during the run — runtime image, builder
#      stage or intermediate commit (see "Naming is not enough" below).
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
# Finally it tears the instance and the probe store down and re-checks, because
# a gate that fills a disk every run is its own version of the bug. That teardown
# and its re-check run on BOTH paths — see "...and leave nothing behind" at the
# bottom, and reap_leaked_build. A run that FAILS is a run that just put an image
# build somewhere it should not be, so it is the run whose cleanup matters most,
# and it was the one that used to skip the check entirely (de-y5g).
#
# NAMING IS NOT ENOUGH, hence 2. setup.sh builds `mtgc:latest` and then tags
# `mtgc:<instance>`, and `mtgc:latest` is a name prod's own deploy writes too —
# so a leaked build cannot be recognised by that tag, its untagged stage commits
# have no name at all, and the Containerfile's BUILDER STAGE is a full 983 MB
# image that is neither tagged nor an ancestor of the runtime image, so walking
# `image history` from the tag does not reach it either. All of them do carry a
# label the Containerfile applies as the first instruction of each stage, which
# is what this looks for. Anything already in the default store at baseline —
# python:3.12-slim, mtgc:prod, the other instances' images — is ignored, so only
# what ARRIVED during the run can fail. That is exact, and it does not care what
# the leak was called.
#
# The same list is what cleanup removes, so the gate cannot detect a leak it
# then leaves on the disk (de-y5g).
#
# THE BYTE DELTA IS A SECOND INSTRUMENT, AND IT IS CONDITIONAL (de-dk3).
# $HOME/.local/share/containers is not ours. On the deployment box it is a
# shared, multi-tenant store: deckdumpster prod, pokedumpster prod and its
# litestream sidecar, that project's lakehouse pipeline, and every other
# instance nobody relocated all live in it and write to it continuously. `du`
# reports bytes; it cannot report a writer. This gate first failed on PR #285
# for exactly that reason — 820 MB, none of it ours, all of it a neighbouring
# project's prod deploy building and restarting inside our four-minute window.
#
# So the delta is still measured, still compared against
# MTGC_STORE_GATE_TOLERANCE_KB, and still hard — but only when the default
# store's own inventory of images, containers and volumes is unchanged across
# the run, which is the gate's evidence that nobody else was writing. When
# something else was, the neighbours are named in the output and the byte
# comparison is reported instead of asserted, because a number that cannot be
# attributed is not evidence.
#
# Assertion 1 is unconditional and immune to all of it — it names this instance's
# own objects, and nothing else on the box makes an mtgc-store-gate anything.
# Assertion 2 identifies by a label that deckdumpster's PROD DEPLOY also stamps,
# so it is unconditional only while no prod deploy is building; the gate now
# takes a lock to guarantee that rather than assume it, and says so in its output
# when it could not. See "What makes an MTGC build mean this run's" below.
#
# THE TOLERANCE is not zero, and that is measured rather than conceded. Even
# with --root and --runroot set, podman keeps a few things at user scope:
# containers/image writes its blob-info cache to
# $XDG_DATA_HOME/containers/cache/blob-info-cache-v1.boltdb, and
# $HOME/.config/containers is config that has nothing to do with the store. That
# is kilobytes. The default is set well above what was observed and far below
# an image layer, so the gate has room for podman's bookkeeping and none at all
# for a leaked build.
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

# What the default store holds, as one line per object, stable enough to diff
# before against after. Images come from --all so a build's untagged stage
# commits are in it too: a neighbouring project building during our window is
# precisely what this has to be able to see.
# The `sed` is not cosmetic: --no-trunc renders an image ID as sha256:<hex>,
# while `image inspect` and `image history` hand back bare hex, and the identity
# check below compares the two. Without it every ID looks new, including the
# base image, and the gate fails on its own first run.
default_store_inventory() {
    podman images --all --no-trunc --format 'image {{.ID}} {{.Repository}}:{{.Tag}}' 2>/dev/null |
        sed -E 's/^image sha256:/image /'
    podman ps --all --format 'container {{.ID}} {{.Names}}' 2>/dev/null
    podman volume ls --format 'volume {{.Name}}' 2>/dev/null
}

# The instance's own Quadlet is where its store is recorded, so the probe store
# is queried the same way teardown.sh finds it — through the unit, not through a
# variable this script happens to be holding.
probe_args() {
    sed -n 's/^GlobalArgs=//p' "$QUADLET_FILE" | head -n1
}

probe_store_has() {
    local args
    args="$(probe_args)"
    [ -n "$args" ] || return 1
    # shellcheck disable=SC2086  # the store root is charset-validated by store-lib.sh
    podman $args "$1" exists "$2" >/dev/null 2>&1
}

# Every image an MTGC build produced in a given store: the runtime image, the
# builder stage, and every intermediate layer commit in both. They carry a label
# the Containerfile applies as the first instruction of each stage, which is the
# only thing that finds all of them.
#
# Walking `image history` from mtgc:<instance> does NOT, and that was a 983 MB
# blind spot rather than a stylistic difference: the Containerfile is
# multi-stage, and the builder stage is a full image that is untagged and is not
# an ancestor of the runtime image, so it appears in neither the tag nor the
# history. Measured while reproducing de-y5g — a leaked build left fifteen
# images in the default store and a history walk accounted for five of them.
#
# `--all` because most of these are untagged; `--no-trunc` because these IDs are
# compared against `default_store_inventory`, which prints them in full. Bare
# `podman`, deliberately: like the two functions above, this is the default
# store — the one under test.
#
# One row per TAG comes back, so a leaked build reports its runtime image twice
# — once as mtgc:<instance>, once as mtgc:latest. Deduped, or the failure output
# names it twice and the reap counts it twice.
mtgc_build_image_ids() {
    podman images --all --no-trunc --filter label=cards.dumpster.mtgc.build=1 \
        --format '{{.ID}}' 2>/dev/null |
        sed -E 's/^sha256://' | grep -v '^$' | awk '!seen[$0]++' || true
}

IMAGE="mtgc:${INSTANCE}"
VOLUME="mtgc-${INSTANCE}-data"
CONTAINER="systemd-mtgc-${INSTANCE}"

# --- Teardown, which must also run when an assertion fails ------------------

STORE_ENV_WAS_THERE=true
[ -f "$STORE_ENV" ] || STORE_ENV_WAS_THERE=false

WORK="$(mktemp -d)"

# MTGC build images that ARRIVED in the default store during this run — the
# leak, if there is one. Both halves matter: the label says "an MTGC build built
# this", and absence from the baseline says "during our window". The box
# legitimately holds mtgc:prod and older instances' images, and they are none of
# our business.
#
# What makes "an MTGC build" mean "this run's" is that nothing else is building
# one while we measure. That used to be a property of the box — CI and the prod
# deploy shared a single self-hosted runner, which runs one job at a time — and
# the version of this comment that said so also said what would happen if it
# stopped holding: "it would fail a gate run and remove an image the box would
# rebuild". It stopped holding on 2026-08-30 (4c5d9b2, a second runner for the
# `deploy` label on the same box), and the consequence was worse than predicted:
# the removal landed on a build that was still RUNNING, so the box did not
# rebuild it, the deploy died on the missing layer, and that merge never reached
# prod.
#
# The neighbouring projects that write to this store continuously (see "The byte
# delta" above) still do not build MTGC images, so they remain invisible here.
# deckdumpster's own prod deploy is the one writer that is indistinguishable
# from us — same Containerfile, same base, and podman layers are
# content-addressed, so its layers and ours are not merely similar but the same
# IDs. No comparison can separate them after the fact.
#
# So exclusion replaces attribution: mtgc_default_store_lock (store-lib.sh) is
# held across the whole measurement, and deploy/deploy.sh takes the same lock
# around a default-store build. HELD_LOCK below records whether we actually got
# it, because a gate that assumes it did is back to resting on a convention.
leaked_image_ids() {
    [ -f "$WORK/image-ids-before" ] || return 0
    mtgc_build_image_ids | grep -vxF -f "$WORK/image-ids-before" || true
}

# reap_leaked_build — if this run's build landed in the DEFAULT store, remove it
# from there (de-y5g).
#
# On a PASSING run this finds nothing: the build went into the probe store,
# which is `rm -rf`'d wholesale. It only ever bites on a FAILING run — which is
# exactly the case the gate exists to detect, and exactly the case that used to
# leave ~1 GB behind on the disk prod runs from. Compounded by CI: deploy/ci.sh's
# `podman image prune -f` runs AFTER store selection, so it is shim-scoped to
# the alternate store and never collects these. A PR that fails the gate
# repeatedly added about a gigabyte per run.
#
# With no baseline recorded — cleanup firing before the measurement was taken —
# nothing can be attributed to this run, so nothing is removed.
#
# Removal is iterated rather than done in one pass because these images are a
# parent chain: `podman rmi` refuses an image another image is built on, and the
# listing order is not a topological one. Each pass strips the current leaves.
# Bounded, so a genuinely unremovable image is reported by the assertions below
# instead of spinning here.
#
# Each removal goes through mtgc_remove_default_store_build_image (store-lib.sh),
# which is the OTHER bound on this cleanup and the one that does not depend on
# the lock: an image with a container on it, or wearing another instance's name,
# is left alone and reported. `podman rmi -f` here — where -f means "remove the
# containers using this image first" — is what took prod down for 15.5 hours on
# 2026-08-30 (de-z9xj). A refusal is remembered, because the image stays in
# leaked_image_ids and would otherwise be re-refused on every pass.
reap_leaked_build() {
    local before after remaining=0 pass id rc
    # Without the lock, an arrival cannot be shown to be ours, and `podman rmi
    # -f` on someone else's in-flight build is how a gate run took prod's deploy
    # down on 2026-08-30. Leaving ~1 GB on the disk is the lesser bug, and it is
    # reported here rather than left silent.
    if [ "${HELD_LOCK:-false}" != true ]; then
        if [ -n "$(leaked_image_ids)" ]; then
            echo "    NOT removing the MTGC images that arrived: this run never held" \
                 "the default-store lock, so they cannot be shown to be ours."
        fi
        return 0
    fi
    before="$(size_kb "$DEFAULT_STORE")"

    : > "$WORK/reap-refused"
    for pass in 1 2 3 4 5; do
        remaining=0
        while read -r id; do
            [ -n "$id" ] || continue
            if grep -qxF "$id" "$WORK/reap-refused"; then
                continue
            fi
            remaining=$((remaining + 1))
            rc=0
            mtgc_remove_default_store_build_image "$id" "$INSTANCE" || rc=$?
            if [ "$rc" -eq 1 ]; then
                printf '%s\n' "$id" >> "$WORK/reap-refused"
            fi
        done < <(leaked_image_ids)
        [ "$remaining" -gt 0 ] || break
    done

    after="$(size_kb "$DEFAULT_STORE")"
    [ "$after" -lt "$before" ] || return 0
    echo "    Removed the images this run left in $DEFAULT_STORE" \
         "(freed $((before - after)) KB)."
}

cleanup() {
    echo "==> Cleaning up"
    reap_leaked_build
    bash "$REPO_DIR/deploy/teardown.sh" "$INSTANCE" --purge >/dev/null 2>&1 || true
    MTGC_STORE_ROOT="$PROBE" bash "$REPO_DIR/deploy/store-teardown.sh" >/dev/null 2>&1 || true
    rm -rf "$PROBE"
    # setup.sh scaffolds this commented-out on a box that has none. Harmless,
    # but "leave nothing behind" means nothing.
    [ "$STORE_ENV_WAS_THERE" = true ] || rm -f "$STORE_ENV"
}
trap 'cleanup; rm -rf "$WORK"' EXIT

# Exclusive from here to the end of cleanup: the baseline, the bring-up, the
# assertions and the reap all assume the default store's MTGC inventory changes
# only because of us. 30 minutes is far past a build; reaching it means a holder
# is stuck, not busy.
#
# A timeout does NOT fail the gate. Every real assertion still runs — this only
# decides whether new MTGC arrivals can be blamed on us — and a PR going red
# because a deploy happened to overlap it is precisely the noise that gets a
# gate's tolerance raised until it means nothing.
HELD_LOCK=false
echo "==> Taking the default-store lock..."
if mtgc_default_store_lock "${MTGC_STORE_GATE_LOCK_TIMEOUT:-1800}"; then
    HELD_LOCK=true
else
    echo "    WARNING: could not take it in 30m. Assertion 2 (identity) will be"
    echo "             reported rather than asserted, and nothing will be reaped."
fi

# A previous run that died mid-flight leaves an instance behind, and its image
# would then be a pre-existing byte the measurement blames on this run.
bash "$REPO_DIR/deploy/teardown.sh" "$INSTANCE" --purge >/dev/null 2>&1 || true

BEFORE_KB="$(size_kb "$DEFAULT_STORE")"
# Taken before the bring-up for two jobs: telling our leak from a neighbour's
# afterwards, and telling an image the box already had (the build's base image,
# most obviously) from one that arrived during the run.
default_store_inventory | sort > "$WORK/inventory-before"
# Split out here rather than at the assertion, because the cleanup that reaps a
# leaked build needs it too and may fire before the assertions are ever reached.
awk '$1 == "image" { print $2 }' "$WORK/inventory-before" > "$WORK/image-ids-before"
echo "    Default store before: ${BEFORE_KB} KB, $(wc -l < "$WORK/inventory-before") objects"

# --- The thing being gated --------------------------------------------------

echo "==> MTGC_STORE_ROOT=$PROBE bash deploy/setup.sh $INSTANCE --test"
MTGC_STORE_ROOT="$PROBE" bash "$REPO_DIR/deploy/setup.sh" "$INSTANCE" --test

AFTER_KB="$(size_kb "$DEFAULT_STORE")"
PROBE_KB="$(size_kb "$PROBE")"
GREW_KB=$((AFTER_KB - BEFORE_KB))

default_store_inventory | sort > "$WORK/inventory-after"
comm -3 "$WORK/inventory-before" "$WORK/inventory-after" > "$WORK/inventory-changed"

echo ""
echo "==> Results"
echo "    Default store: ${BEFORE_KB} -> ${AFTER_KB} KB  (${GREW_KB} KB, tolerance ${TOLERANCE_KB})"
echo "    Probe store:   ${PROBE_KB} KB  (floor ${FLOOR_KB})"

FAILED=false
fail() {
    echo "FAIL: $*" >&2
    FAILED=true
}

# 1. NEGATIVE, by name.
if default_store_has image "$IMAGE"; then
    fail "$IMAGE is in Podman's default store — the disk prod runs from."
fi
if default_store_has volume "$VOLUME"; then
    fail "$VOLUME is in Podman's default store — the disk prod runs from."
fi
# systemd does not inherit the PATH shim, so an unstamped Quadlet starts the
# instance out of the default store; the container is the artefact that leaves.
if default_store_has container "$CONTAINER"; then
    fail "$CONTAINER is in Podman's default store — systemd started this" \
         "instance out of the disk prod runs from."
fi

# 2. NEGATIVE, by identity. Names would miss a leaked build: its only tag is
#    mtgc:latest, which prod's own deploy writes too, and its stage commits and
#    builder stage have no tag at all. The Containerfile's build label is what
#    finds them, and the baseline is what dates them to this run.
while read -r id; do
    [ -n "$id" ] || continue
    if [ "$HELD_LOCK" = true ]; then
        fail "image ${id:0:12} — an MTGC build image — arrived in Podman's default" \
             "store during this run. A build leaked onto the disk prod runs from."
    else
        echo "    NOTE: image ${id:0:12} — an MTGC build image — arrived in the" \
             "default store, but this run never held the lock, so it cannot be" \
             "told from a concurrent prod deploy's. Reported, not asserted."
    fi
done < <(leaked_image_ids)

# THE BYTE DELTA, the second instrument — hard, but only while it is
# attributable. $HOME/.local/share/containers is shared with every other project
# on the box and `du` cannot say who wrote what (de-dk3). An unchanged object
# inventory is the evidence that nobody else did.
if [ ! -s "$WORK/inventory-changed" ]; then
    if [ "$GREW_KB" -gt "$TOLERANCE_KB" ]; then
        fail "$DEFAULT_STORE grew by ${GREW_KB} KB, over the ${TOLERANCE_KB} KB tolerance."
    fi
else
    echo "    NOTE: the default store is shared, and something else wrote to it"
    echo "          during this run. The byte delta above is reported, not"
    echo "          asserted; the checks that name and identify this instance's"
    echo "          own objects are unaffected. What changed:"
    head -n 20 "$WORK/inventory-changed" | sed 's/^/            /'
    if [ "$(wc -l < "$WORK/inventory-changed")" -gt 20 ]; then
        echo "            ... $(($(wc -l < "$WORK/inventory-changed") - 20)) more"
    fi
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
fi

# --- ...and leave nothing behind -------------------------------------------
#
# THIS RUNS ON BOTH PATHS, and that is the fix for de-y5g rather than a tidiness
# preference. It used to sit under an `exit 1`, so the one kind of run where
# leftovers were possible — one that had just put a build in the default store —
# was the one kind of run that never checked for them. cleanup() itself did fire
# (it is the EXIT trap), but it removed only mtgc:<instance>, which was a tag on
# an image mtgc:latest still held; measured, that left 983 MB on / per failing
# run. reap_leaked_build in cleanup() is the other half.

cleanup
trap 'rm -rf "$WORK"' EXIT

FINAL_KB="$(size_kb "$DEFAULT_STORE")"
LEFT_KB=$((FINAL_KB - BEFORE_KB))
echo "    Default store after cleanup: ${FINAL_KB} KB  (${LEFT_KB} KB vs baseline)"

# Same two instruments, same order of trust: what teardown left behind of OURS
# is a fact about the names, and the byte figure is only evidence when nothing
# else touched the store. `fail`, not `exit`, so a leaked run reports both what
# it leaked and what it then failed to clean up, in one output.
if default_store_has image "$IMAGE" || default_store_has volume "$VOLUME" \
   || default_store_has container "$CONTAINER"; then
    fail "cleanup left this instance's objects in $DEFAULT_STORE."
fi
default_store_inventory | sort > "$WORK/inventory-final"
if cmp -s "$WORK/inventory-before" "$WORK/inventory-final"; then
    if [ "$LEFT_KB" -gt "$TOLERANCE_KB" ]; then
        fail "cleanup left ${LEFT_KB} KB behind in $DEFAULT_STORE."
    fi
else
    # Two ways to get here, and they read the same in `du`: a neighbouring
    # project wrote during our window, or our own leaked build displaced an
    # image the box already had to <none>:<none> — a dangling image that was
    # there at baseline, so not ours to remove. Report, do not assert.
    echo "    NOTE: the default store's inventory differs from baseline, so the"
    echo "          ${LEFT_KB} KB figure above is reported, not asserted. The"
    echo "          check by name directly above is unaffected. What changed:"
    comm -3 "$WORK/inventory-before" "$WORK/inventory-final" | head -n 20 | sed 's/^/            /'
fi
if [ -e "$PROBE" ]; then
    fail "the probe store is still on disk: $PROBE"
fi
if [ -f "$QUADLET_FILE" ]; then
    fail "cleanup left the Quadlet behind: $QUADLET_FILE"
fi

if [ "$FAILED" = true ]; then
    exit 1
fi

echo ""
echo "==> PASS — a --test bring-up wrote nothing to Podman's default store."
