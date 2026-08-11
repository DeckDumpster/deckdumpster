#!/usr/bin/env bash
#
# Where an MTGC instance's container storage lives (de-3mo).
#
# Rootless Podman keeps images, layers and volumes under $HOME. On the box that
# runs prod, $HOME is on the 98G LVM root that PROD ITSELF RUNS FROM — measured
# 2026-08-11, podman's store was 34G of the 74G used on /. So every throwaway
# `--test` instance, every CI image build and every dangling layer is written to
# the disk prod serves from. / has hit 100% twice, once producing
# `ld terminated with signal 7 [Bus error]`, which reads as a toolchain bug and
# not a disk problem, and cost real diagnosis time.
#
# The fix is NOT to move Podman's store wholesale — that would relocate prod's
# volumes (mtgc-prod-data, 19G) as a side effect, which is a durability decision
# nobody asked for. Instead this is an OPT-IN alternate store for non-prod:
#
#   MTGC_STORE_ROOT=<dir>   put images, layers and volumes under <dir>
#   MTGC_STORE_ROOT=        (unset/empty) use Podman's default store
#
# Prod never opts in, so prod's behaviour is untouched by construction rather
# than by a conditional that has to get prod right. With the variable empty,
# every function here returns immediately and the generated Quadlet unit comes
# out byte-identical to what it was before this file existed.
#
# This is a port of pokedumpster's deploy/store-lib.sh (pd-fite, pd-9rxf,
# pd-rkrf, pd-yfev). The mechanism, the naming and the failure modes below were
# measured there; keep the two in step rather than diverging.
#
# WHERE THE VALUE COMES FROM
#
# Which disk is worth using is a fact about one machine, so it is not in the
# repo: mtgc_store_load_config reads it from ~/.config/mtgc/store.env, the same
# host-config directory default.env and the per-instance <instance>.env files
# already live in. It is NOT inferred from the box's disk layout — a rule like
# "the checkout is on a different filesystem from $HOME" encodes one machine's
# topology and would silently invent a store directory at the top of an external
# drive or a network mount on any other box.
#
# Only the callers that MAY use an alternate store read that file:
# .github/workflows/ci.yml and deploy/store-teardown.sh. setup.sh, deploy.sh and
# teardown.sh honour the environment and nothing else, because setup.sh is also
# how prod is installed and a host config file does not get to decide where
# prod's volumes live.
#
# HOW IT IS APPLIED
#
# Two consumers have to agree, or you get an instance whose image lives in one
# store and whose container looks for it in another:
#
#   1. Shell scripts. mtgc_store_activate installs a `podman` shim on PATH that
#      adds --root/--runroot to every invocation. A shim rather than an argument
#      threaded through each call site because deploy/ has ~50 podman calls
#      across eight scripts and missing ONE fails silently, in the exact way
#      described above. PATH is inherited, so children agree for free — which is
#      what makes setup.sh -> restore.sh, and pytest -> `podman exec`, correct
#      without either of them knowing about stores.
#   2. Units systemd runs. systemd does not inherit our PATH, so the generated
#      units carry the same flags: mtgc_store_stamp_unit writes a GlobalArgs=
#      key into the Quadlet (Podman 4.9's Quadlet applies GlobalArgs to
#      ExecStart, ExecStop and ExecStopPost alike, so start and stop use one
#      store), and mtgc_store_stamp_service rewrites the `podman exec` lines in
#      the per-instance price/sealed-catalog/EDHREC timer units. Those are
#      rendered per instance rather than being one %i template, so unlike
#      pokedumpster's they CAN carry per-instance flags.
#
# THE UNIT IS THE RECORD, IN BOTH DIRECTIONS
#
# Because PATH is inherited, a script that operates on an EXISTING instance
# cannot just take the ambient store: it has to ask the instance where it lives.
# mtgc_store_adopt_instance does that, and it has to be able to answer "the
# default store" as positively as it answers "that one over there" — an
# unstamped unit is a statement, not a missing value. Measured on pokedumpster
# (pd-9rxf), an add-only version produced two mirror-image failures:
#
#   * teardown.sh, run inside a shell that had activated an alternate store,
#     aimed `podman rmi` / `podman volume rm` at a store the instance was never
#     in. Both no-op'd through their `2>/dev/null || true`, and then teardown
#     deleted the unit — the only record of where the image and volume were.
#   * deploy.sh built and tagged into the alternate store while the unstamped
#     unit kept systemd on the default one, so the restart succeeded and went
#     on serving the OLD image.
#
# Hence mtgc_store_deactivate: adopting an unstamped unit drops the shim from
# PATH and clears the flags, rather than falling through.
#
# TMPDIR moves too. deckdumpster's Containerfile bind-mounts ~/.cache/uv rather
# than using `--mount=type=cache`, so there is no Buildah cache to relocate, but
# image-pull and build staging still land in TMPDIR (/var/tmp by default, i.e.
# the prod disk). Pointing it inside the store root also keeps staging on the
# same filesystem as the store it is about to be moved into.
#
# ############################################################################
# # NEVER RUN `podman system reset` — IT IS NOT SCOPED BY --root/--runroot.  #
# ############################################################################
#
# Everything above teaches operators and scripts to pass --root/--runroot at a
# second store. `system reset` is the one subcommand that ignores them, and it
# sits one keystroke away from the store you actually want to delete. It says so
# itself: `podman system reset --help` is "Reset podman storage back to default
# state" — default, not "the state of the store you named".
#
# Measured on podman 4.9.3, 2026-08-08 (pd-rkrf). Cleaning up a THROWAWAY probe
# store with
#
#     podman --root=<probe>/storage --runroot=<probe-runroot> system reset --force
#
# also wiped user-global rootless state that no flag pointed at: /run/user/$UID/libpod
# and the rootless SHM lock (podman's per-user runtime state, shared by EVERY
# store on the box, prod's included) and the Buildah cache at the AMBIENT
# TMPDIR. Result: prod went down — HTTP 000, podman answering "container state
# improper" while the server process was still alive; other instances left in
# state `Created` with live conmon, still serving but unmanageable. Data
# survived; the damage was runtime state, repaired by
# `systemctl --user restart mtgc-<instance>` per affected instance.
#
# REMOVING A STORE, correctly. Stop and remove what the store owns, from inside
# that store, then delete its directories. Every command below IS scoped by the
# flags, so run them with the shim on PATH (mtgc_store_activate) or pass
# $MTGC_STORE_GLOBAL_ARGS explicitly:
#
#     podman stop -a                      # or teardown.sh per instance first
#     podman rm -af
#     podman volume rm -af                # the store's volumes, nobody else's
#     podman rmi -af
#     podman network prune -f
#     rm -rf "$MTGC_STORE_ROOT" "${MTGC_STORE_GLOBAL_ARGS##*--runroot=}"
#
# The store root is storage/ + tmp/ + bin/ (the shim); the runroot is read back
# off the flags rather than globbed, so it is the one derived for THIS graph
# root and not another store's. `rm -rf` on the two directories is the part
# `system reset` was being reached for, and it is scoped by construction: a path
# deletes exactly the path. The shim is inside the store root, so a shell that
# ran this has a PATH entry pointing at nothing — start a new one.
#
# mtgc_store_teardown runs exactly that recipe, and deploy/store-teardown.sh is
# the CLI over it. Any store-removal command added to deploy/ must use it; that
# is not left to memory — tests/test_deploy_store.py greps deploy/ and fails on
# a `podman system reset` anywhere in it.
#
# Sourced, not executed.

# mtgc_store_load_config — take MTGC_STORE_ROOT from host config when the caller
# has not set it. Called only by the scripts that MAY use an alternate store;
# never by the ones prod runs, so prod cannot pick one up from a file it did not
# ask about.
#
# Precedence, and the distinction is load-bearing:
#
#   MTGC_STORE_ROOT set (even to empty)   the caller decided — file ignored
#   MTGC_STORE_ROOT unset                 read ~/.config/mtgc/store.env
#   neither                               Podman's default store
#
# An explicit empty value has to win, because that is how a one-off run opts
# back out on a box whose store.env opts in.
mtgc_store_load_config() {
    [ -z "${MTGC_STORE_ROOT+set}" ] || return 0
    local conf="${HOME}/.config/mtgc/store.env"
    [ -f "$conf" ] || return 0
    # Same shape as default.env and <instance>.env: a dotenv file, sourced.
    set -a
    # shellcheck disable=SC1090
    . "$conf"
    set +a
}

# mtgc_store_validate — a store root has to be an absolute path made of
# characters that survive being pasted into a systemd unit and a sed
# replacement. Rejecting loudly beats a unit whose GlobalArgs= is silently
# truncated at a space or a '|', which would send systemd to the DEFAULT store
# — prod's — while every script in this process tree used the alternate one.
mtgc_store_validate() {
    case "$1" in
        /) echo "ERROR: MTGC_STORE_ROOT must not be /" >&2; return 1 ;;
        /*) ;;
        *) echo "ERROR: MTGC_STORE_ROOT must be an absolute path, got: $1" >&2; return 1 ;;
    esac
    case "$1" in
        *[!A-Za-z0-9._/+@-]*)
            echo "ERROR: MTGC_STORE_ROOT may only contain A-Z a-z 0-9 . _ / + @ -" >&2
            echo "       got: $1" >&2
            return 1
            ;;
    esac
}

# mtgc_store_activate — point every podman invocation in this process tree at
# $MTGC_STORE_ROOT. Idempotent; a no-op when the variable is unset or empty.
#
# Exports MTGC_STORE_GLOBAL_ARGS (the flags, for the stamp functions) and
# MTGC_STORE_ROOT itself, so a child script that sources this file again sees
# the same store instead of re-deriving one.
mtgc_store_activate() {
    export MTGC_STORE_GLOBAL_ARGS="${MTGC_STORE_GLOBAL_ARGS:-}"
    [ -n "${MTGC_STORE_ROOT:-}" ] || return 0

    local root graph runroot bin real
    # Normalise the trailing slash so the same directory always produces the
    # same graph root, hence the same runroot and the same GlobalArgs — but not
    # for "/" itself, which must reach the validator intact to be named in the
    # error rather than reported as an empty path.
    root="$MTGC_STORE_ROOT"
    [ "$root" = "/" ] || root="${root%/}"
    mtgc_store_validate "$root" || return 1
    export MTGC_STORE_ROOT="$root"
    bin="${root}/bin"

    # Already activated in an ancestor: the shim is on PATH and the flags are in
    # the environment. Re-shimming here would resolve `podman` to the shim and
    # build one that exec's itself.
    case ":${PATH}:" in
        *":${bin}:"*) return 0 ;;
    esac

    real="$(command -v podman)" || {
        echo "ERROR: MTGC_STORE_ROOT is set but podman is not on PATH" >&2
        return 1
    }

    graph="${root}/storage"
    # Remembered so mtgc_store_deactivate can put it back; see there.
    export MTGC_STORE_PREV_TMPDIR="${TMPDIR-}"
    # The runroot holds volatile per-boot state, including the layer store's
    # mountpoints.json — a file each store rewrites wholesale. Two stores sharing
    # one would drop each other's mount records, and prod is one of those stores.
    # It has to be on a local filesystem, so it goes in the runtime dir, keyed by
    # the store it belongs to.
    runroot="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/mtgc-store-$(printf '%s' "$graph" | sha1sum | cut -c1-8)"
    mkdir -p "$graph" "$runroot" "${root}/tmp" "$bin"

    export MTGC_STORE_GLOBAL_ARGS="--root=${graph} --runroot=${runroot}"

    cat > "${bin}/podman" <<EOF
#!/usr/bin/env bash
# Generated by deploy/store-lib.sh — do not edit. Sends every podman call in
# this process tree to the non-prod store under ${root} (de-3mo).
exec ${real} ${MTGC_STORE_GLOBAL_ARGS} "\$@"
EOF
    chmod +x "${bin}/podman"

    export PATH="${bin}:${PATH}"
    export TMPDIR="${root}/tmp"
    # stderr, not stdout: callers parse some of these scripts' stdout (deploy.sh
    # greps `podman port`), and this is a progress note, not a result.
    echo "==> Container storage: ${graph} (non-prod store; prod's is untouched)" >&2

    mtgc_store_netns_repair
}

# mtgc_store_netns_name — the name Podman gives THIS store's rootless network
# namespace. Podman derives it from the libpod static dir, which is <graph>/libpod:
#
#   libpod/networking_linux.go
#     hash := sha256.Sum256([]byte(r.config.Engine.StaticDir))
#     netnsName := fmt.Sprintf("%s-%x", rootlessNetNsName, hash[:10])
#
# Reproducing a hash from another project's internals is not something to do
# lightly. It is done here because it is what makes the repair below SAFE: with
# the name computed from this store's own graph root, prod's name is never even
# derived, so no code path can remove it. The alternative — reaping every
# `rootless-netns-*` in the runtime dir — would have to reason about prod's.
#
# Verified byte-exact against two live stores on podman 4.9.3 (pd-yfev). If a
# future podman changes the scheme this stops matching, the repair silently
# finds nothing, and the failure mode is the status quo ante.
mtgc_store_netns_name() {
    printf 'rootless-netns-%s' \
        "$(printf '%s' "${1}/libpod" | sha256sum | cut -c1-20)"
}

# mtgc_store_netns_repair — un-wedge this store's rootless networking.
#
# THE BUG (pd-yfev). Two rootless stores cannot both keep a network namespace,
# and podman 4.9 does not notice:
#
#   * Each store gets its OWN netns file, named from the hash above, under
#     $XDG_RUNTIME_DIR/netns/.
#   * They SHARE one scaffolding directory, $XDG_RUNTIME_DIR/libpod/tmp/rootless-netns.
#     That path comes from Engine.TmpDir, which --root and --runroot do not move
#     (neither does --tmpdir — measured on 4.9.3).
#   * The scaffolding is created only on the branch that CREATES the netns.
#   * RootlessNetNS.Cleanup() does os.RemoveAll on the SHARED directory when the
#     last bridge-network container *in its own store* exits — it counts
#     containers out of its own store's database and cannot see the other one's.
#
# So the moment one store's last container on a user-defined network goes away,
# every OTHER store is left holding a netns file that still looks valid. Podman
# takes it, skips the create branch, and then fails to mount into scaffolding
# that is no longer there:
#
#   Error: failed to mount runtime directory for rootless netns: no such file or directory
#
# That store can never start a container on a user-defined network again, and it
# wedges silently, mid-session, with nothing in the message to suggest "store".
#
# deckdumpster's Quadlet template sets no Network=, so its containers use the
# default rootless networking and do not create that scaffolding today. This is
# insurance, not a live bug here: it costs one stat when no netns file exists,
# and the day someone adds a user-defined network it is already handled.
#
# THE REPAIR is to delete this store's stale netns file, which puts podman back
# on the create branch. It is not a mountpoint in our mount namespace (the mount
# lives in the pause process's), so removing the name is all it takes.
#
# It is deliberately NOT `podman system migrate`, which is the repair found by
# hand first: migrate kills the pause process, and that process is per-USER, not
# per-store — shared with the default store prod runs in. A non-prod convenience
# must not reach into prod's runtime state to fix itself.
#
# The guard is what keeps this from being a live-namespace killer: if the shared
# scaffolding is present, some store is using it, and nothing is removed.
mtgc_store_netns_repair() {
    [ -n "${MTGC_STORE_ROOT:-}" ] || return 0

    local rundir netns_file
    rundir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    netns_file="${rundir}/netns/$(mtgc_store_netns_name "${MTGC_STORE_ROOT}/storage")"

    # Nothing of ours to reap.
    [ -e "$netns_file" ] || return 0
    # Scaffolding intact — the netns is usable, and may be in use right now.
    [ -d "${rundir}/libpod/tmp/rootless-netns/run/user/$(id -u)" ] && return 0

    echo "==> Rootless netns for this store is stale (another store's cleanup removed" >&2
    echo "    the shared scaffolding). Dropping ${netns_file##*/} so podman rebuilds it." >&2
    rm -f "$netns_file"
}

# mtgc_store_teardown — remove the active store: every container and image in
# it, the store root (graph, TMPDIR and the shim), its runroot, and its netns
# name. The store-level lifecycle command — deploy/teardown.sh removes an
# INSTANCE and deliberately leaves the store it lived in alone, so without this
# a box accumulates stores nothing ever collects.
#
# This is the "REMOVING A STORE, correctly" recipe in this file's header, made
# executable. Never `podman system reset`, which ignores --root/--runroot and
# took prod down when it was aimed at a throwaway store (pd-rkrf) — a path
# deletes exactly the path, however podman resolves things.
#
# It must not run without a store either. With MTGC_STORE_ROOT empty the target
# WOULD be Podman's default store, which is prod's, so that case refuses instead
# of defaulting.
#
# `podman unshare rm -rf` rather than plain rm: a rootless store's layer
# directories are owned by subuids, and rm fails on every one of them with
# EPERM. unshare enters the user namespace where those uids are ours.
mtgc_store_teardown() {
    if [ -z "${MTGC_STORE_ROOT:-}" ]; then
        echo "ERROR: mtgc_store_teardown needs MTGC_STORE_ROOT; refusing to" >&2
        echo "       act on Podman's default store (prod's)." >&2
        return 1
    fi

    # Not optional. Every podman call below is a bare `podman`, which without the
    # shim means Podman's DEFAULT store — so an un-activated teardown would
    # `rm -f -a` prod's containers. Activation is idempotent.
    mtgc_store_activate || return 1

    local root graph rundir netns_file
    root="$MTGC_STORE_ROOT"
    graph="${root}/storage"
    rundir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    netns_file="${rundir}/netns/$(mtgc_store_netns_name "$graph")"

    echo "==> Removing container store ${root}" >&2

    # The recipe, in order, every command scoped by the shim's flags. Best-effort
    # throughout: a store whose database is already gone has nothing to stop, and
    # the directory removal below is what actually frees the disk.
    podman stop -a >/dev/null 2>&1 || true
    podman rm -af >/dev/null 2>&1 || true
    podman volume rm -af >/dev/null 2>&1 || true
    podman rmi -af >/dev/null 2>&1 || true
    podman network prune -f >/dev/null 2>&1 || true
    # The header's recipe ends in `rm -rf` on the store root and its runroot.
    # Two details it does not mention, both measured rather than reasoned
    # (pd-yfev):
    #
    #   * `podman rm -af` returns before the container's rootfs is unmounted, and
    #     one leftover mount fails the whole removal with EBUSY on
    #     storage/overlay. It survived three retries a second apart. So the
    #     unmount and the removal happen inside ONE `podman unshare` — the mount
    #     is in that namespace, and a second invocation is a second namespace
    #     that cannot see it.
    #   * It cannot be the last word. This `podman` IS the doomed store's shim,
    #     so podman re-creates that store's skeleton as it shuts down — after the
    #     command inside it has exited. storage.lock, overlay/ and
    #     overlay-layers/ come back every time. What comes back is empty and ours
    #     (not subuid-owned), so a plain rm finishes the job.
    #
    # bin/ (the shim this call is running through) goes with it: podman has
    # already exec'd, so the script being deleted underneath it is harmless.
    podman unshare sh -c '
        root=$1
        while read -r _ _ _ _ mp _; do
            case "$mp" in "$root"|"$root"/*) printf "%s\n" "$mp" ;; esac
        done < /proc/self/mountinfo | sort -r | while read -r mp; do
            umount -l "$mp" 2>/dev/null || true
        done
        rm -rf "$root"
    ' sh "$root" >/dev/null 2>&1 || true
    rm -rf "$root" 2>/dev/null || true

    # The volatile state goes either way — it is this store's alone (the runroot
    # is keyed by the graph path) and is worthless without the store.
    rm -rf "${rundir}/mtgc-store-$(printf '%s' "$graph" | sha1sum | cut -c1-8)"
    rm -f "$netns_file"

    # Say what is actually true. A teardown that reports success over a store it
    # could not remove is worse than one that fails: the disk it was supposed to
    # free stays full and nothing says so.
    if [ -e "$root" ]; then
        echo "ERROR: ${root} is still on disk — something in it is still mounted." >&2
        echo "       Stop anything using this store and run this again." >&2
        return 1
    fi
}

# mtgc_store_is_activated — is the store named by MTGC_STORE_ROOT the one this
# process tree's `podman` actually resolves to? The shim on PATH is the marker:
# mtgc_store_activate always puts it there.
#
# This is what separates a store the caller CHOSE for this call from one merely
# inherited from a parent that activated it, and the two are not the same claim.
# `MTGC_STORE_ROOT=/x bash deploy/teardown.sh foo` is a decision about foo — the
# escape hatch for a unit that is missing or wrong — and the variable is set with
# no shim on PATH. A CI job activating a store and then invoking teardown.sh for
# some OTHER instance says nothing about that instance, and the variable arrives
# WITH the shim.
mtgc_store_is_activated() {
    [ -n "${MTGC_STORE_ROOT:-}" ] || return 1
    case ":${PATH}:" in
        *":${MTGC_STORE_ROOT%/}/bin:"*) return 0 ;;
    esac
    return 1
}

# mtgc_store_deactivate — put this process tree back on Podman's default store:
# drop the shim from PATH, restore TMPDIR, clear the flags. The inverse of
# mtgc_store_activate, and the reason adopt can select the default store
# positively instead of by omission.
#
# PATH and TMPDIR are touched only when a store is genuinely active, so on prod —
# which never opts in — this is nothing but two empty exports. Clearing
# MTGC_STORE_GLOBAL_ARGS is what stops the stamp functions from writing a store
# into a unit that must not carry one; exporting MTGC_STORE_ROOT empty (rather
# than unsetting it) says "the default store, decided" in the vocabulary
# mtgc_store_load_config already reads.
mtgc_store_deactivate() {
    if mtgc_store_is_activated; then
        local bin="${MTGC_STORE_ROOT%/}/bin"
        PATH="${PATH//":${bin}:"/:}"
        PATH="${PATH#"${bin}:"}"
        PATH="${PATH%":${bin}"}"
        export PATH
        TMPDIR="${MTGC_STORE_PREV_TMPDIR-}"
        [ -n "$TMPDIR" ] || unset TMPDIR
    fi
    export MTGC_STORE_ROOT=""
    export MTGC_STORE_GLOBAL_ARGS=""
}

# mtgc_store_adopt_instance <instance> — put this shell on the store the instance
# actually lives in, read from its installed Quadlet unit, so that
# `deploy/teardown.sh <instance>` removes from the SAME store setup created it
# in and `deploy/deploy.sh <instance>` builds into the one systemd will look in.
#
# The unit is authoritative in both directions: GlobalArgs names a store, and no
# GlobalArgs names the default store just as definitely. What it does not do is
# invent a store — with no unit on disk there is no record to read (the instance
# may not exist yet; deploy.sh delegates to setup.sh), so the caller's choice
# stands.
#
# An explicit MTGC_STORE_ROOT still beats the unit; an inherited activation does
# not. See mtgc_store_is_activated for why those are different.
mtgc_store_adopt_instance() {
    local unit graph
    unit="${HOME}/.config/containers/systemd/mtgc-${1}.container"
    [ -f "$unit" ] || return 0

    if [ -n "${MTGC_STORE_ROOT:-}" ] && ! mtgc_store_is_activated; then
        return 0
    fi

    graph="$(sed -n 's/^GlobalArgs=.*--root=\([^ ]*\).*/\1/p' "$unit" | head -n1)"
    if [ -z "$graph" ]; then
        mtgc_store_deactivate
        return 0
    fi

    graph="${graph%/storage}"
    if [ "${MTGC_STORE_ROOT:-}" != "$graph" ]; then
        # Leave the store we are on before naming another, so PATH carries one
        # shim and TMPDIR belongs to the store it points at.
        mtgc_store_deactivate
        MTGC_STORE_ROOT="$graph"
    fi
}

# mtgc_store_stamp_unit <quadlet file> — teach a generated Quadlet unit to use
# the active store. A no-op when no store is active, which is what keeps prod's
# generated unit byte-identical to the pre-de-3mo one.
mtgc_store_stamp_unit() {
    [ -n "${MTGC_STORE_GLOBAL_ARGS:-}" ] || return 0
    sed -i "/^\[Container\]\$/a GlobalArgs=${MTGC_STORE_GLOBAL_ARGS}" "$1"
}

# mtgc_store_stamp_service <systemd service file> — same job for the per-instance
# timer units (prices, sealed-catalog, EDHREC), whose ExecStart lines shell out
# to `podman exec`. systemd runs them with its own PATH, so the shim is not
# there; the flags have to be in the file. A no-op when no store is active.
#
# Unlike pokedumpster's, these units are rendered per instance rather than being
# one %i template shared by every instance, so they can carry per-instance flags
# and there is no reason to leave them uncovered. Without this an alternate-store
# instance's timers fire against the DEFAULT store and fail with "no such
# container" — recoverable, but only after someone reads the journal.
mtgc_store_stamp_service() {
    [ -n "${MTGC_STORE_GLOBAL_ARGS:-}" ] || return 0
    # ExecStart= lines only, and only where `podman` is the word being run —
    # mtgc-edhrec.service wraps two calls in `/bin/sh -c '...'`, so this has to
    # match inside the quoted string too, not just at the head of the line.
    sed -i "/^ExecStart=/ s|\\bpodman |podman ${MTGC_STORE_GLOBAL_ARGS} |g" "$1"
}
