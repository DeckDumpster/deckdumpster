"""The container-store isolation gate, observed failing (de-3a0).

`deploy/store-isolation-gate.sh` runs a real `deploy/setup.sh <name> --test`
against real podman and asserts the bytes landed in the alternate store rather
than Podman's default one — the disk prod runs from. That takes an image build,
so it runs as its own CI step, not here.

What runs here is the gate's own judgement. A gate is only worth having if it
goes red when it should, and "I unset the variable once and watched it fail" is
a fact about an afternoon, not a property of the repo. So these drive the real
gate script with podman stubbed, and the stub is told where to put the bytes:

    honoured     podman respects --root           -> the gate passes
    ignored      podman writes to $HOME anyway    -> fails, naming the leak
    nothing      the build silently no-ops        -> fails as vacuous
    latest_only  the build leaks, tagged only
                 `mtgc:latest` — a name prod
                 writes too                       -> fails on the image ID
    spill        bytes appear in the default
                 store with no object to name     -> fails on the byte delta
    neighbour    another project writes to the
                 shared default store while we
                 measure                          -> PASSES (de-dk3)

`nothing` is the one that is easy to leave out and the reason the gate asserts
positives at all: a bring-up that did nothing writes nothing to the default
store either, and would sail through a gate that only checked for the leak.

`neighbour` is the inverse, and it is a real regression rather than a
hypothetical: the gate's first CI run failed on 820 MB that a sibling project's
prod deploy wrote to the same shared store during our window. A gate that goes
red when someone else builds is a gate that gets its tolerance raised until it
stops meaning anything. `spill` is what keeps that fix honest — the byte delta
is still hard when nothing else touched the store.

Same shape as tests/test_deploy_store.py — stubbed podman/systemctl/loginctl and
a throwaway $HOME, so the real scripts run end to end. The stub keeps a registry
of which store it "created" each image, volume and container in, which is what
lets `podman image exists` answer differently per store.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "deploy" / "store-isolation-gate.sh"

# Written by `build`, so one bring-up produces one predictable lump. Real ones
# are ~1.9 GiB; the thresholds below are scaled to match, not the other way
# round, so the arithmetic under test is the same arithmetic.
STUB_MB = 8

# Image IDs the stub hands out. The build produces two: the runtime image, which
# gets tagged, and the BUILDER STAGE, which does not — a real multi-stage build
# commits it as a full ~1 GB image that is untagged and is not an ancestor of
# the runtime image, so neither a tag nor `image history` reaches it. Only the
# Containerfile's build label does, which is why the gate looks for that
# (de-y5g). The base image's ID is there to prove the hunt ignores what the box
# already had; python:3.12-slim legitimately lives in the default store.
BUILT_ID = "b" * 64
STAGE_ID = "5a9e" + "0" * 60
BASE_ID = "ba5e" + "0" * 60
NEIGHBOUR_ID = "17" * 32

# Records every call, then acts out one of the worlds above. $STUB_MODE picks.
#
# The `--root=`/`--runroot=` prefix is what store-lib.sh's shim prepends; the
# graph root it names is this call's store, and no prefix means Podman's
# default. In `ignored` mode the stub reads the flags and then behaves as if it
# had not — which is exactly the regression the gate exists to catch, whether it
# comes from a broken shim, a call site that bypassed it, or a podman that
# stopped honouring the flag.
PODMAN_STUB = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PODMAN_LOG"

GRAPH=""
while [ $# -gt 0 ]; do
    case "$1" in
        --root=*) GRAPH="${1#--root=}"; shift ;;
        --runroot=*) shift ;;
        *) break ;;
    esac
done

[ "$STUB_MODE" = "ignored" ] && GRAPH=""

DEFAULT_STORAGE="$HOME/.local/share/containers/storage"

# One registry file per store, outside every store so it is never mistaken for
# store bytes by the gate's `du`. Lines are "<kind> <name> <id> <ours>", where
# `ours` is 1 for an image an MTGC build produced — the stub's stand-in for the
# Containerfile's `cards.dumpster.mtgc.build` label, which is what the gate
# filters on. The base image and the neighbouring project's are 0, and that is
# what makes "a build leaked" distinguishable from "the box already had this".
reg() {
    printf '%s/%s' "$STUB_STATE" "$(printf '%s' "${GRAPH:-default}" | tr -c 'A-Za-z0-9' _)"
}

record()   { [ "$STUB_MODE" = "nothing" ] && return 0; printf '%s %s %s %s\n' "$1" "$2" "${3:--}" "${4:-0}" >> "$(reg)"; }
# By name OR id, because `rmi` is given an ID and the rows it has to take out
# are tagged: one image with two tags is two rows.
unrecord() { r="$(reg)"; [ -f "$r" ] || return 0; awk -v k="$1" -v n="$2" '!($1==k && ($2==n || $3==n))' "$r" > "$r.new" || true; mv "$r.new" "$r"; }
has()      { r="$(reg)"; [ -f "$r" ] || return 1; awk -v k="$1" -v n="$2" '$1==k && ($2==n || $3==n) {f=1} END{exit !f}' "$r"; }
id_of()    { r="$(reg)"; [ -f "$r" ] || return 0; awk -v n="$1" '$1=="image" && ($2==n || $3==n) {print $3; exit}' "$r"; }
ours_of()  { r="$(reg)"; [ -f "$r" ] || return 0; awk -v n="$1" '$1=="image" && ($2==n || $3==n) {print $4; exit}' "$r"; }

# One byte lump per image, named after its ID, so `rmi` frees exactly that
# image's bytes and a run can be measured for what its cleanup got back. Still
# $STUB_MB each, so the tolerance and floor arithmetic is the arithmetic under
# test.
lump() {
    [ "$STUB_MODE" = "nothing" ] && return 0
    target="${2:-${GRAPH:-$DEFAULT_STORAGE}}"
    mkdir -p "$target"
    dd if=/dev/zero of="$target/stub-layer-$1" bs=1M count=$STUB_MB status=none
}

# Bytes into the default store that the honoured path never puts there. Which
# of them also registers an OBJECT is the whole distinction the gate now draws.
leak_into_default() {
    mkdir -p "$DEFAULT_STORAGE"
    dd if=/dev/zero of="$DEFAULT_STORAGE/$1" bs=1M count=$STUB_MB status=none
}

# `podman cp` out of a container is how setup.sh gets the fixture onto the host
# before tarring it, so it has to leave a real file behind or the tar fails and
# the gate never reaches its assertions. Into a container (a DST with a colon)
# there is nothing to fake.
fake_cp() {
    case "$2" in *:*) return 0 ;; esac
    case "${1##*/}" in
        *.sqlite) : > "$2" ;;
        *) mkdir -p "$2" ;;
    esac
}

case "${1:-}" in
    --version) echo "podman version 0.0.0-stub" ;;
    build)
        # A real multi-stage build commits TWO images: the runtime one, which
        # setup.sh then tags, and the builder stage, which nothing names and
        # which is not an ancestor of the runtime image. Both carry the label.
        record image mtgc:latest "$STUB_BUILT_ID" 1
        record image '<none>:<none>' "$STUB_STAGE_ID" 1
        lump "$STUB_BUILT_ID"
        lump "$STUB_STAGE_ID"
        case "$STUB_MODE" in
            latest_only)
                printf 'image %s %s 1\n' mtgc:latest "$STUB_BUILT_ID" >> "$STUB_STATE/default"
                lump "$STUB_BUILT_ID" "$DEFAULT_STORAGE" ;;
            neighbour)
                printf 'image %s %s 0\n' neighbour:prod "$STUB_NEIGHBOUR_ID" >> "$STUB_STATE/default"
                leak_into_default neighbour-layer ;;
            spill)
                leak_into_default spilled-blobs ;;
        esac
        ;;
    tag)    record image "$3" "$(id_of "$2")" "$(ours_of "$2")" ;;
    rmi)
        shift
        while [ $# -gt 0 ]; do
            case "$1" in -f|--force) shift ;; *) break ;; esac
        done
        rmi_id="$(id_of "$1")"
        [ -n "$rmi_id" ] || rmi_id="$1"
        unrecord image "$1"
        rm -f "${GRAPH:-$DEFAULT_STORAGE}/stub-layer-$rmi_id"
        ;;
    ps)     r="$(reg)"; [ -f "$r" ] && awk '$1=="container" {print "container " $2 " " $2}' "$r" ;;
    # --no-trunc renders an ID as sha256:<hex> here and bare hex from `inspect`
    # and `history`, which is a difference the gate has to reconcile and so has
    # to be reproduced.
    #
    # Under the label filter only the images an MTGC build produced come back,
    # and undeduped: one image with two tags is two rows, which is what makes
    # the gate's own dedup worth having.
    images)
        r="$(reg)"; [ -f "$r" ] || exit 0
        case "$*" in
            *label=cards.dumpster.mtgc.build=1*)
                awk '$1=="image" && $4=="1" {print "sha256:" $3}' "$r" ;;
            *)
                awk '$1=="image" {print "image sha256:" $3 " " $2}' "$r" ;;
        esac
        ;;
    container) [ "${2:-}" = "exists" ] && { has container "$3" || exit 1; } ;;
    image)
        case "${2:-}" in
            exists) has image "$3" || exit 1 ;;
            inspect) has image "${!#}" && id_of "${!#}" ;;
            # A real history lists the stages, then the base image's layers,
            # then the ones that came in with the base and have no image of
            # their own.
            history) has image "${!#}" && printf '%s\n<missing>\n%s\n' "$STUB_BUILT_ID" "$STUB_BASE_ID" ;;
        esac
        ;;
    volume)
        case "${2:-}" in
            create) record volume "$3" ;;
            rm) unrecord volume "$3" ;;
            exists) has volume "$3" || exit 1 ;;
            ls) r="$(reg)"; [ -f "$r" ] && awk '$1=="volume" {print "volume " $2}' "$r" ;;
        esac
        ;;
    cp) fake_cp "$2" "$3" ;;
esac
exit 0
"""

NOOP_STUB = "#!/usr/bin/env bash\nexit 0\n"
LINGER_STUB = "#!/usr/bin/env bash\necho 'Linger=yes'\nexit 0\n"


def run_gate(tmp_path, mode):
    """Drive the real gate in a throwaway $HOME with podman acting out `mode`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("podman", PODMAN_STUB),
        ("systemctl", NOOP_STUB),
        ("loginctl", LINGER_STUB),
    ):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)

    home = tmp_path / "home"
    # A default store that already holds something, so the gate is measuring a
    # delta rather than the difference between nothing and something.
    default_store = home / ".local/share/containers/storage"
    default_store.mkdir(parents=True)
    (default_store / "existing").write_bytes(b"\0" * (4 << 20))

    state = tmp_path / "stub-state"
    state.mkdir()
    # The default store already holds the build's base image, as the real one
    # does. The gate must not mistake it for a leak just because it turns up in
    # our image's history.
    # Trailing 0: not an MTGC build image, so the label filter must not return
    # it however often it turns up in our own build's history.
    (state / "default").write_text(f"image docker.io/library/python:3.12-slim {BASE_ID} 0\n")

    env = dict(os.environ)
    env.update(
        HOME=str(home),
        PATH=f"{bin_dir}:{env['PATH']}",
        XDG_RUNTIME_DIR=str(tmp_path / "run"),
        PODMAN_LOG=str(tmp_path / "podman.log"),
        STUB_MODE=mode,
        STUB_STATE=str(state),
        STUB_MB=str(STUB_MB),
        STUB_BUILT_ID=BUILT_ID,
        STUB_STAGE_ID=STAGE_ID,
        STUB_BASE_ID=BASE_ID,
        STUB_NEIGHBOUR_ID=NEIGHBOUR_ID,
        MTGC_STORE_GATE_ROOT=str(tmp_path / "probe"),
        # Scaled to STUB_MB: half of one lump is over the tolerance and under
        # the floor, so a lump in the wrong place trips the negative and a
        # missing lump trips the positive.
        MTGC_STORE_GATE_TOLERANCE_KB=str(STUB_MB * 1024 // 2),
        MTGC_STORE_GATE_FLOOR_KB=str(STUB_MB * 1024 // 2),
    )
    # Inherited from the developer's own shell these would aim the gate at a
    # real store on the box.
    env.pop("MTGC_STORE_ROOT", None)
    env.pop("MTGC_STORE_GLOBAL_ARGS", None)

    return subprocess.run(
        ["bash", str(GATE), "gatetest"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def default_store_kb(tmp_path):
    """What is actually on the disk afterwards, rather than what the gate says
    is. The gate reports its own byte figure, and de-y5g was a run that reported
    honestly and still left the bytes there."""
    store = tmp_path / "home/.local/share/containers/storage"
    return sum(f.stat().st_size for f in store.rglob("*") if f.is_file()) // 1024


@pytest.fixture(scope="module")
def honoured(tmp_path_factory):
    return run_gate(tmp_path_factory.mktemp("honoured"), "honoured")


@pytest.fixture(scope="module")
def ignored(tmp_path_factory):
    """The failing run, kept so several things can be asked of one of them —
    what it said, and what it left behind."""
    tmp_path = tmp_path_factory.mktemp("ignored")
    return run_gate(tmp_path, "ignored"), tmp_path


def test_it_passes_when_podman_honours_the_store(honoured):
    assert honoured.returncode == 0, honoured.stdout + honoured.stderr
    assert "PASS" in honoured.stdout


def test_it_leaves_neither_store_behind(honoured):
    """A gate that fills a disk every run is its own version of the bug."""
    assert "Default store after cleanup" in honoured.stdout, honoured.stdout


def test_it_fails_when_the_bytes_land_in_the_default_store(ignored):
    """The regression itself: podman writing to $HOME despite --root."""
    result, _ = ignored

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Podman's default store" in output, output


def test_a_failing_run_leaves_nothing_in_the_default_store(ignored):
    """de-y5g. The gate used to `exit 1` before its own leave-nothing-behind
    check, and its cleanup removed only the mtgc:<instance> TAG — off an image
    mtgc:latest still held. So the one kind of run that had just put a build on
    the disk prod runs from was the one kind that left it there: measured, 983
    MB per failing run, and CI's `podman image prune -f` never collected them
    because it is shim-scoped to the alternate store.

    Measured off the directory, not off the gate's report."""
    result, tmp_path = ignored

    assert result.returncode != 0, result.stdout + result.stderr
    # The 4 MB the store already held, and not one lump more.
    assert default_store_kb(tmp_path) < (4 * 1024) + (STUB_MB * 1024 // 2)


def test_a_failing_run_names_the_untagged_builder_stage(ignored):
    """The 983 MB blind spot. A multi-stage build's builder stage is a full
    image that nothing tags and that is not an ancestor of the runtime image, so
    neither the tag nor `image history` reaches it — only the Containerfile's
    label does.

    On a FAIL line specifically: the stage turns up in the inventory diff the
    gate prints either way, and a gate that merely mentions an image it did not
    fail on is the gate this replaces."""
    result, _ = ignored
    output = result.stdout + result.stderr

    failures = [ln for ln in output.splitlines() if ln.startswith("FAIL:")]
    assert any(STAGE_ID[:12] in ln for ln in failures), output


def test_a_failing_run_still_reports_what_it_cleaned_up(ignored):
    """The check itself moved below the FAILED branch, so both paths reach it.
    A failing run is the one whose leftovers matter."""
    result, _ = ignored

    assert "Default store after cleanup" in result.stdout, result.stdout


def test_it_fails_when_the_leak_is_tagged_only_mtgc_latest(tmp_path):
    """Names cannot catch this one. setup.sh builds `mtgc:latest` before it tags
    the instance, and prod's own deploy writes that same tag — so a build that
    leaked is recognisable only by the ID it produced."""
    result = run_gate(tmp_path, "latest_only")

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "A build leaked" in output, output


def test_it_fails_when_bytes_appear_with_no_object_to_name(tmp_path):
    """The byte delta is the instrument that catches a spill nothing is named
    after, and it is still hard when nothing else touched the store."""
    result = run_gate(tmp_path, "spill")

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "over the" in output and "tolerance" in output, output


def test_a_neighbour_writing_to_the_shared_store_does_not_fail_it(tmp_path):
    """de-dk3. $HOME/.local/share/containers is shared with every other project
    on the deployment box, and `du` cannot say who wrote what. The gate's first
    CI run went red on 820 MB of a sibling project's prod deploy. It must report
    the neighbour and go green, because the alternative is a required check that
    fails at random until someone raises the tolerance."""
    result = run_gate(tmp_path, "neighbour")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "PASS" in output, output
    # Reported, not silently swallowed: the delta is over tolerance and the gate
    # says so, along with who else was writing.
    assert "reported, not" in output, output
    assert "neighbour:prod" in output, output


def test_it_fails_when_nothing_was_built_at_all(tmp_path):
    """The vacuous pass. Nothing leaked because nothing happened, and a gate
    that only looks for the leak calls that success."""
    result = run_gate(tmp_path, "nothing")

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "nothing was built" in output, output


def test_it_refuses_a_probe_store_inside_the_store_under_test(tmp_path):
    """Then the gate would be comparing a directory with itself."""
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        MTGC_STORE_GATE_ROOT=str(home / ".local/share/containers/probe"),
    )
    env.pop("MTGC_STORE_ROOT", None)

    result = subprocess.run(
        ["bash", str(GATE), "gatetest"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode != 0
    assert "the store under test" in result.stdout + result.stderr


def test_it_refuses_to_run_against_prod():
    """It builds an instance and then destroys it."""
    result = subprocess.run(
        ["bash", str(GATE), "prod"], capture_output=True, text=True, cwd=str(REPO_ROOT)
    )

    assert result.returncode != 0
    assert "Not prod" in result.stdout + result.stderr


def test_ci_runs_the_gate():
    """Anything CI does not invoke is a hand-only check, and this one exists
    precisely because the convention it guards was never checked.

    CI is `ci.yml` -> `deploy/ci.sh` -> the gate (de-xz8), so both links are
    asserted: a gate invoked from a script nothing calls is still hand-only.
    """
    workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text()
    ci = (REPO_ROOT / "deploy/ci.sh").read_text()

    assert "deploy/ci.sh" in workflow
    assert "deploy/store-isolation-gate.sh" in ci
