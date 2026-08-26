#!/usr/bin/env bash
#
# Low-disk checks for the box that runs prod (de-yef). Two modes, one threshold
# source, one place to reason about how full is too full.
#
#   diskcheck.sh                     ALERT mode. Pushes a Pushover alert when a
#                                    watched filesystem is at or over
#                                    MTGC_DISK_THRESHOLD percent used. Always
#                                    exits 0 on a healthy disk — it is a timer,
#                                    not a gate.
#
#   diskcheck.sh --floor [path...]   GATE mode. Exits NON-ZERO when any named
#                                    path's filesystem has less than
#                                    MTGC_DISK_FLOOR_GB free. Run before work
#                                    that needs room; deploy/setup.sh and CI
#                                    both call it.
#
# WHY THIS EXISTS
#
# / on the deployment box is 98G and prod serves from it. It has hit 100% twice
# — 2026-08-08 and 2026-08-11 — and on both of those nights the mtgc backup
# silently did not run (de-o4e). Nothing said so, either time. de-3mo moved
# non-prod container bytes off that disk and de-3a0 proves in CI that they stay
# off, so the largest producer is bounded; what was still missing is anyone
# NOTICING the disk fill for any of the reasons that remain — prod's own volume,
# the price time series, another project on the same box, a stray tarball.
#
# The second half is the gate. Running out mid-build does not announce itself as
# a disk problem: at 697M free a cargo link died with
# `ld terminated with signal 7 [Bus error]` and exit 101, which reads as a
# broken toolchain and cost real diagnosis time.
#
# Mirrors pokedumpster:deploy/diskcheck.sh, which is where both failure modes
# were measured; keep the two in step rather than diverging. The one deliberate
# divergence is below: the sibling watches a single path, and MTGC has a second
# disk worth watching because MTGC_STORE_ROOT put one there.
#
# WHICH FILESYSTEMS
#
# Two disks matter here and they are not the same disk: prod's ($HOME, where
# rootless Podman keeps prod's 19G volume) and the non-prod container store
# (MTGC_STORE_ROOT, if this box opted in). Both are watched, deduplicated by
# device, so a box that never opted in checks exactly one filesystem and behaves
# as if this paragraph were not here.
#
# Reading store.env to learn a path to WATCH is not the store selection that
# deploy/setup.sh scopes away from prod — nothing here moves a byte or picks a
# store. It only decides which `df` lines to look at. This script never invokes
# podman, so it does not source deploy/store-lib.sh the way the scripts that do
# must; it restates that file's precedence rule and cites it instead.
#
# Env-driven, from the host-wide ~/.config/mtgc/alerts.env:
#   MTGC_DISK_THRESHOLD   percent-used that triggers an alert (default 90)
#   MTGC_DISK_FLOOR_GB    gigabytes free below which --floor fails (default 10)
#   MTGC_DISK_PATH        the primary filesystem to watch (default $HOME)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Production never sets MTGC_CONFIG_DIR; only tests point it elsewhere, so a
# gate can exercise the shipped script without reading — or depending on — the
# operator's real credentials. Same convention as deploy/backup-check.sh.
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"

# A value passed in the environment beats the one in the file, for every knob
# here — the same precedence store.env already documents for MTGC_STORE_ROOT,
# and what `MTGC_DISK_THRESHOLD=0 bash diskcheck.sh` has to mean for the
# prove-it-goes-red recipe in deploy/README.md to work on a box that HAS
# configured a threshold. Sourcing a dotenv always overwrites, so the three are
# saved first.
ENV_THRESHOLD="${MTGC_DISK_THRESHOLD:-}"
ENV_FLOOR_GB="${MTGC_DISK_FLOOR_GB:-}"
ENV_DISK_PATH="${MTGC_DISK_PATH:-}"

[ -f "${CONF_DIR}/alerts.env" ] && { set -a; . "${CONF_DIR}/alerts.env"; set +a; }

THRESHOLD="${ENV_THRESHOLD:-${MTGC_DISK_THRESHOLD:-90}}"
FLOOR_GB="${ENV_FLOOR_GB:-${MTGC_DISK_FLOOR_GB:-10}}"
DISK_PATH="${ENV_DISK_PATH:-${MTGC_DISK_PATH:-$HOME}}"

# --- Which paths are watched by default -------------------------------------

# store.env names the non-prod container store, i.e. the second disk worth
# watching. The rule for reading it is deploy/store-lib.sh's, restated here
# rather than sourcing the store machinery into a df wrapper: an
# MTGC_STORE_ROOT already in the environment wins, INCLUDING an explicit empty
# one, which is how a single run opts back out.
if [ -z "${MTGC_STORE_ROOT+set}" ] && [ -f "${CONF_DIR}/store.env" ]; then
    set -a; . "${CONF_DIR}/store.env"; set +a
fi

DEFAULT_PATHS=("$DISK_PATH")
[ -n "${MTGC_STORE_ROOT:-}" ] && DEFAULT_PATHS+=("$MTGC_STORE_ROOT")

# resolve_existing — a store root that has not been created yet still sits on
# some mounted filesystem. Walk up until df has something to measure.
resolve_existing() {
    local p="$1"
    while [ ! -e "$p" ] && [ "$p" != "/" ]; do p="$(dirname "$p")"; done
    printf '%s' "$p"
}

# free_gb — whole gigabytes free, TRUNCATED. `df -BG` rounds up, so a disk with
# 9.2G free reports 10G and would clear a 10G floor; the floor exists to be
# conservative, so it reads 1K blocks and divides.
free_gb() {
    local kb
    kb="$(df --output=avail "$1" | tail -n1 | tr -dc '0-9')"
    echo $(( kb / 1048576 ))
}

# watch_list — the filesystems to measure, one resolved path per distinct
# device. Paths on the same device are the same check, and both modes below want
# that, so it is written once.
#
# An empty result is a FAILURE, not a quiet pass. "We could not measure anything"
# and "everything is fine" must never share an outcome — the same rule
# backup-check.sh states, and the reason this file exists at all is that a full
# disk went unreported twice.
watch_list() {
    local -n out="$1"; shift
    mapfile -t out < <(dedupe_by_device "$@")
    if [ "${#out[@]}" -eq 0 ]; then
        echo "diskcheck: FAILED — measured no filesystem at all. df could not read:" >&2
        printf '  %s\n' "$@" >&2
        exit 1
    fi
}

dedupe_by_device() {
    local p dev
    declare -A seen=()
    for p in "$@"; do
        p="$(resolve_existing "$p")"
        dev="$(df --output=source "$p" | tail -n1)"
        [ -z "${seen[$dev]:-}" ] || continue
        seen[$dev]=1
        printf '%s\n' "$p"
    done
}

# --- Gate mode --------------------------------------------------------------

if [ "${1:-}" = "--floor" ]; then
    shift
    PATHS=("$@")
    [ ${#PATHS[@]} -gt 0 ] || PATHS=("${DEFAULT_PATHS[@]}")

    watch_list WATCH "${PATHS[@]}"

    # Every short disk is reported, not just the first: a caller told to free
    # space wants the whole list before it starts deleting things.
    FAILED=0
    for p in "${WATCH[@]}"; do
        FREE="$(free_gb "$p")"
        MOUNT="$(df --output=target "$p" | tail -n1)"
        if [ "$FREE" -lt "$FLOOR_GB" ]; then
            echo "ERROR: only ${FREE}G free on ${MOUNT} (floor ${FLOOR_GB}G)." >&2
            echo "  Work that runs out of room here does NOT fail as a disk error — the" >&2
            echo "  last time this happened a cargo link reported 'ld terminated with" >&2
            echo "  signal 7 [Bus error]'. Free space before re-running." >&2
            echo "  $(df -h "$p" | tail -n1)" >&2
            echo "  Candidates: bash deploy/prune-instances.sh, podman image prune" >&2
            FAILED=1
        else
            echo "diskcheck: ${MOUNT} has ${FREE}G free (floor ${FLOOR_GB}G) — ok"
        fi
    done
    exit "$FAILED"
fi

# --- Alert mode -------------------------------------------------------------

watch_list WATCH "${DEFAULT_PATHS[@]}"

for p in "${WATCH[@]}"; do
    MOUNT="$(df --output=target "$p" | tail -n1)"
    USE="$(df --output=pcent "$p" | tail -n1 | tr -dc '0-9')"
    echo "diskcheck: ${MOUNT} at ${USE}% (threshold ${THRESHOLD}%)"

    if [ "$USE" -ge "$THRESHOLD" ]; then
        "${SCRIPT_DIR}/alert.sh" "MTGC LOW DISK ${MOUNT} (${USE}%)" \
            "$(df -h "$p" | tail -n1) on $(hostname) — over ${THRESHOLD}% threshold"
    fi
done
