"""Every lakehouse chain job is memory-bounded and runs at low priority.

On 2026-10-24 a hand run of mtgc-prices (AllPrintings + AllPricesToday + a
124k-entry UUID map in one process) hung the shared product host: no bound, so
the box thrashed instead of the job dying (sp-3m1ct7). A unit-level MemoryMax
alone does not cover a `podman run` child, which lives in its own scope, so each
podman run also carries --memory.
"""

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
LAKE_UNITS = ("land", "derive", "prices", "ship", "value")


def _text(name):
    return (DEPLOY / f"mtgc-{name}.service").read_text()


def test_every_lake_job_declares_a_memory_bound():
    for name in LAKE_UNITS:
        t = _text(name)
        assert re.search(r"^MemoryMax=\d+[GM]$", t, re.M), f"{name}: no MemoryMax"
        assert re.search(r"^MemorySwapMax=0$", t, re.M), f"{name}: no MemorySwapMax=0"


def test_every_lake_podman_run_is_bounded():
    for name in LAKE_UNITS:
        runs = [l for l in _text(name).splitlines() if "podman run" in l]
        assert runs, name
        for l in runs:
            assert re.search(r"--memory \d+[gm] --memory-swap \d+[gm]", l), f"{name}: {l[:80]}"


def test_every_lake_job_runs_at_low_priority():
    for name in LAKE_UNITS:
        t = _text(name)
        assert re.search(r"^Nice=1\d$", t, re.M), f"{name}: no Nice"
        assert re.search(r"^IOSchedulingClass=idle$", t, re.M), f"{name}: no idle IO class"
        assert re.search(r"^CPUWeight=\d{1,2}$", t, re.M), f"{name}: no low CPUWeight"
