#!/usr/bin/env bash
#
# Refuse to start a container build on a nearly-full disk (de-3ww).
#
#   diskcheck.sh --floor [path...]   Exits NON-ZERO when any named path's
#                                    filesystem has less than MTGC_DISK_FLOOR_GB
#                                    free. With no paths given it checks $HOME.
#
# WHY A GATE AND NOT A WARNING. Running out of room mid-build does not announce
# itself as a disk problem. On this project's deployment box / has hit 100%
# twice; one of those produced `ld terminated with signal 7 [Bus error]` from a
# cargo link, which reads as a broken toolchain and cost real diagnosis time.
# The failure is cheap to prevent and expensive to recognise, so the build is
# refused before it starts rather than diagnosed after it dies.
#
# WHY TWO PATHS. de-3mo gave non-prod container bytes somewhere else to live
# (MTGC_STORE_ROOT, see deploy/store-lib.sh), but it moved the container STORE
# only. $HOME still holds the uv cache the Containerfile bind-mounts and the
# default store prod's own volumes live in, so both disks still matter and both
# have to be asked. Every caller passes the pair:
#
#     bash deploy/diskcheck.sh --floor "$HOME" "${MTGC_STORE_ROOT:-$HOME}"
#
# Unset, those are the same directory and the same filesystem — reported once,
# because the output names disks rather than repeating one under two aliases.
#
# THE FLOOR. 10G by default, against a ~100G disk: an image build writes on the
# order of 1G, so this is roughly five times the room a build needs and trips at
# about 90% used. It is deliberately not tighter. The deploy path this most
# needs to protect is prod's, and prod's is also the one that must not be made
# to fail spuriously — but a prod deploy attempted with under 10G free is a
# deploy that would likely have died half-built, and refusing is the better of
# those two outcomes. Override host-wide in ~/.config/mtgc/alerts.env:
#
#     MTGC_DISK_FLOOR_GB=20
#
# Precedence is environment, then that file, then the default — the same order
# store-lib.sh gives MTGC_STORE_ROOT. The file says what this BOX needs free;
# the environment says what THIS RUN needs.
#
# PORTED FROM pokedumpster's deploy/diskcheck.sh (pd-fite); keep the two in step
# rather than letting them diverge. Two deliberate differences:
#
#   * Only the --floor gate is ported. pokedumpster's script is also a Layer 4
#     low-disk ALERT run by a timer; deckdumpster has no such timer, and
#     shipping an alert mode nothing runs would be dead code. Bare invocation is
#     a usage error (exit 2), not a silent no-op — that is the seam the alert
#     half would slot into, tracked as de-ax9.
#   * `df -Pk` plus awk instead of GNU `df --output=`, so the script also runs
#     by hand on the macOS deployment path, where BSD df has no --output. POSIX
#     guarantees -P puts each filesystem on one line, so the field positions
#     below are stable.
#
# WHO CALLS IT: every path that builds an image on Linux — .github/workflows/ci.yml,
# deploy/setup.sh, deploy/deploy.sh, deploy/seed.sh. deploy/store-isolation-gate.sh
# gets it through the setup.sh it runs. deploy/mac-setup.sh and deploy/mac-deploy.sh
# deliberately do NOT call it: there the build's bytes land inside the podman
# machine's VM disk, so a host-side df measures a filesystem the build is not
# filling and the gate would be answering the wrong question.
#
set -euo pipefail

# Production never sets MTGC_CONFIG_DIR; only tests point it elsewhere, so a
# gate can exercise the shipped script without reading the operator's real file.
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"

# Precedence: environment, then the host file, then the built-in default — the
# same order store-lib.sh gives MTGC_STORE_ROOT. Sourcing alerts.env would
# otherwise overwrite the variable, so the run's own value is taken first: the
# file says what this BOX needs free, the environment says what THIS RUN needs.
_ENV_FLOOR="${MTGC_DISK_FLOOR_GB:-}"
[ -f "${CONF_DIR}/alerts.env" ] && { set -a; . "${CONF_DIR}/alerts.env"; set +a; }
FLOOR_GB="${_ENV_FLOOR:-${MTGC_DISK_FLOOR_GB:-10}}"

if [ "${1:-}" != "--floor" ]; then
    echo "Usage: bash deploy/diskcheck.sh --floor [path...]" >&2
    echo "  Exits non-zero when a path's filesystem has under \${MTGC_DISK_FLOOR_GB}G free." >&2
    echo "  There is no alert mode here — see the header." >&2
    exit 2
fi
shift

case "$FLOOR_GB" in
    ''|*[!0-9]*)
        echo "diskcheck: MTGC_DISK_FLOOR_GB is '${FLOOR_GB}', which is not a whole number of GB." >&2
        echo "  Fix it in ${CONF_DIR}/alerts.env or the environment." >&2
        exit 2
        ;;
esac

PATHS=("$@")
[ ${#PATHS[@]} -gt 0 ] || PATHS=("$HOME")

# Paths on one filesystem are one check — the output names disks, not arguments.
# Keyed on the MOUNT POINT, which is unique per filesystem, and not on the device
# the way pokedumpster's does: `tmpfs` and `overlay` are the reported source for
# every one of their mounts, so two genuinely different filesystems collapse into
# one and the second never gets measured. A plain string rather than an
# associative array so this still runs under the bash 3.2 macOS ships.
SEEN="|"
FAILED=0

for p in "${PATHS[@]}"; do
    # A store root that does not exist yet still sits on some mounted
    # filesystem — walk up until df has something to measure.
    while [ ! -e "$p" ] && [ "$p" != "/" ]; do p="$(dirname "$p")"; done

    # POSIX `df -P` writes one line per filesystem, so: 1 source, 2 total,
    # 3 used, 4 available, 5 capacity, 6.. mount point. -k makes those KiB.
    # df's own stderr is left alone; a path this cannot measure is a FAILURE of
    # the gate, because a gate that does not know how much room there is must
    # not be the thing that says there is enough.
    DF_LINE="$(df -Pk "$p" | awk 'NR==2 {
        dev = $1; avail = $4
        $1 = $2 = $3 = $4 = $5 = ""; sub(/^ +/, "")   # what is left is the mount
        print dev, avail, $0
    }')" || true
    if [ -z "$DF_LINE" ]; then
        echo "ERROR: df could not measure ${p} — refusing to build without knowing the free space." >&2
        FAILED=1
        continue
    fi
    read -r _DEV AVAIL_KB MOUNT <<EOF
$DF_LINE
EOF

    # Delimited with | rather than a space, because a mount point may contain one.
    case "$SEEN" in *"|${MOUNT}|"*) continue ;; esac
    SEEN="${SEEN}${MOUNT}|"

    FREE_GB=$(( AVAIL_KB / 1024 / 1024 ))
    if [ "$FREE_GB" -lt "$FLOOR_GB" ]; then
        echo "ERROR: only ${FREE_GB}G free on ${MOUNT} (floor ${FLOOR_GB}G)." >&2
        echo "  Builds that run out of room here do NOT fail as disk errors — the" >&2
        echo "  last time this happened a link step reported 'ld terminated with" >&2
        echo "  signal 7 [Bus error]'. Free space before re-running." >&2
        echo "  $(df -h "$p" | tail -n1)" >&2
        FAILED=1
    else
        echo "diskcheck: ${MOUNT} has ${FREE_GB}G free (floor ${FLOOR_GB}G) — ok"
    fi
done

exit "$FAILED"
