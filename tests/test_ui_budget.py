"""The UI suite's timeout budgets measure the app, not the box it runs on.

de-6q2: a `tests/ui -k sets_` run on the shared deployment box produced 14
failures, every one a Playwright timeout and not one an assertion — including a
click whose call log shows it succeeded and navigated. These tests pin the two
properties that keep that from recurring without giving up the 500 ms budget
`tests/ui/` exists to enforce.
"""

import ast
from pathlib import Path

import pytest

from tests.ui import budget
from tests.ui.budget import (
    INTERACTION_BUDGET_MS,
    ROUND_TRIP_BUDGET_MS,
    TIMEOUT_CEILING_MS,
    budget_ms,
    host_contention,
)

UI_DIR = Path(__file__).parent / "ui"


# ── The budget on a quiet box ────────────────────────────────────────────────


def test_an_unloaded_box_gets_exactly_the_old_timeouts():
    """The measurement this suite exists for is unchanged where you take it.

    Normalization is only allowed to spend patience the host took away. With
    nothing taken away it must spend none, or the 500 ms budget has quietly
    become 500 ms of something else.
    """
    assert budget_ms(INTERACTION_BUDGET_MS, 1.0) == 500
    assert budget_ms(ROUND_TRIP_BUDGET_MS, 1.0) == 5_000


def test_contention_floors_at_one_on_an_idle_box(monkeypatch):
    """An idle box does not earn a *shorter* budget than the stated one."""
    monkeypatch.setattr(budget.os, "getloadavg", lambda: (0.0, 0.0, 0.0))
    monkeypatch.setattr(budget.os, "cpu_count", lambda: 8)
    assert host_contention() == 1.0
    assert budget_ms(INTERACTION_BUDGET_MS) == INTERACTION_BUDGET_MS


def test_contention_is_runnable_tasks_per_cpu(monkeypatch):
    monkeypatch.setattr(budget.os, "getloadavg", lambda: (24.0, 0.0, 0.0))
    monkeypatch.setattr(budget.os, "cpu_count", lambda: 4)
    assert host_contention() == 6.0


# ── The budget on a loaded box ───────────────────────────────────────────────


def test_the_budget_scales_with_contention():
    """8x oversubscribed means 8x the wall clock buys the same app time."""
    assert budget_ms(INTERACTION_BUDGET_MS, 8.0) == 4_000


def test_inflation_stops_at_the_ceiling():
    """Past where Playwright itself gives up, contention stops being the story."""
    assert budget_ms(INTERACTION_BUDGET_MS, 1_000.0) == TIMEOUT_CEILING_MS


def test_the_ceiling_never_shrinks_a_timeout_that_was_asked_for():
    """A scenario that explicitly wants 60s still gets 60s on a quiet box.

    The ceiling caps what contention may *add*; it is not a maximum the caller
    is held to. Otherwise wiring an existing generous wait through the budget
    would silently tighten it.
    """
    generous = TIMEOUT_CEILING_MS * 2
    assert budget_ms(generous, 1.0) == generous
    assert budget_ms(generous, 100.0) == generous


# ── One budget, not a literal per call site ──────────────────────────────────

#: Every module that drives Playwright against a live instance in CI.
_TIMEOUT_CALL_SITES = [
    UI_DIR / "replay.py",
    UI_DIR / "harness.py",
    UI_DIR / "test_nav_reachability.py",
]


def _bare_numeric_timeouts(path: Path) -> list[str]:
    """Every `timeout=<number>` written as a literal rather than a budget."""
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "timeout" and isinstance(kw.value, ast.Constant):
                found.append(f"{path.name}:{kw.value.lineno} timeout={kw.value.value}")
    return found


@pytest.mark.parametrize("path", _TIMEOUT_CALL_SITES, ids=lambda p: p.name)
def test_no_call_site_hardcodes_its_own_timeout(path):
    """The regression this whole change is about is a literal per call site.

    With a 500 written at every call, raising the budget means finding all of
    them, and the ones nobody found are the ones that flake. Route it through
    `budget_ms` instead — then there is one place the number lives and one place
    host contention gets applied.
    """
    bare = _bare_numeric_timeouts(path)
    assert not bare, "timeouts must come from tests/ui/budget.py: " + ", ".join(bare)


def test_a_scenario_holds_one_contention_factor_for_its_whole_run(monkeypatch):
    """Re-sampling per step would make a failure unreproducible from its log.

    Two steps of one scenario running against different deadlines is a test you
    cannot read: the log says 500 ms and 4000 ms for the same budget.
    """
    monkeypatch.setattr(budget, "host_contention", lambda: 4.0)
    from tests.ui import replay

    monkeypatch.setattr(replay, "host_contention", lambda: 4.0)
    harness = replay.ReplayHarness(None, "https://localhost", Path("."), "t")

    monkeypatch.setattr(replay, "host_contention", lambda: 40.0)
    assert harness._budget(INTERACTION_BUDGET_MS) == 2_000
    assert harness._budget(ROUND_TRIP_BUDGET_MS) == 20_000
