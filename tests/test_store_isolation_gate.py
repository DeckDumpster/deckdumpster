"""The container-store isolation gate, observed failing (de-3a0).

`deploy/store-isolation-gate.sh` runs a real `deploy/setup.sh <name> --test`
against real podman and asserts the bytes landed in the alternate store rather
than Podman's default one — the disk prod runs from. That takes an image build,
so it runs as its own CI step, not here.

What runs here is the gate's own judgement. A gate is only worth having if it
goes red when it should, and "I unset the variable once and watched it fail" is
a fact about an afternoon, not a property of the repo. So these drive the real
gate script with podman stubbed, and the stub is told where to put the bytes:

    honoured   podman respects --root         -> the gate passes
    ignored    podman writes to $HOME anyway  -> the gate fails, naming the leak
    nothing    the build silently no-ops      -> the gate fails as vacuous

The third is the one that is easy to leave out and the reason the gate asserts
positives at all: a bring-up that did nothing writes nothing to the default
store either, and would sail through a gate that only checked for the leak.

Same shape as tests/test_deploy_store.py — stubbed podman/systemctl/loginctl and
a throwaway $HOME, so the real scripts run end to end. The stub keeps a registry
of which store it "created" each image and volume in, which is what lets
`podman image exists` answer differently per store.
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

# Records every call, then acts out one of three worlds. $STUB_MODE picks which.
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

# One registry file per store, outside every store so it is never mistaken for
# store bytes by the gate's `du`.
reg() {
    printf '%s/%s' "$STUB_STATE" "$(printf '%s' "${GRAPH:-default}" | tr -c 'A-Za-z0-9' _)"
}

record()   { [ "$STUB_MODE" = "nothing" ] && return 0; echo "$1/$2" >> "$(reg)"; }
unrecord() { r="$(reg)"; [ -f "$r" ] || return 0; grep -vxF "$1/$2" "$r" > "$r.new" || true; mv "$r.new" "$r"; }
has()      { r="$(reg)"; [ -f "$r" ] && grep -qxF "$1/$2" "$r"; }

layers() {
    [ "$STUB_MODE" = "nothing" ] && return 0
    target="${GRAPH:-$HOME/.local/share/containers/storage}"
    mkdir -p "$target"
    dd if=/dev/zero of="$target/stub-layer" bs=1M count=$STUB_MB status=none
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
    build)  record image mtgc:latest; layers ;;
    tag)    record image "$3" ;;
    rmi)    unrecord image "$2" ;;
    image)  [ "${2:-}" = "exists" ] && { has image "$3" || exit 1; } ;;
    volume)
        case "${2:-}" in
            create) record volume "$3" ;;
            rm) unrecord volume "$3" ;;
            exists) has volume "$3" || exit 1 ;;
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

    env = dict(os.environ)
    env.update(
        HOME=str(home),
        PATH=f"{bin_dir}:{env['PATH']}",
        XDG_RUNTIME_DIR=str(tmp_path / "run"),
        PODMAN_LOG=str(tmp_path / "podman.log"),
        STUB_MODE=mode,
        STUB_STATE=str(state),
        STUB_MB=str(STUB_MB),
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


@pytest.fixture(scope="module")
def honoured(tmp_path_factory):
    return run_gate(tmp_path_factory.mktemp("honoured"), "honoured")


def test_it_passes_when_podman_honours_the_store(honoured):
    assert honoured.returncode == 0, honoured.stdout + honoured.stderr
    assert "PASS" in honoured.stdout


def test_it_leaves_neither_store_behind(honoured):
    """A gate that fills a disk every run is its own version of the bug."""
    assert "Default store after cleanup" in honoured.stdout, honoured.stdout


def test_it_fails_when_the_bytes_land_in_the_default_store(tmp_path):
    """The regression itself: podman writing to $HOME despite --root."""
    result = run_gate(tmp_path, "ignored")

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Podman's default store" in output, output


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
    precisely because the convention it guards was never checked."""
    workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text()

    assert "deploy/store-isolation-gate.sh" in workflow
