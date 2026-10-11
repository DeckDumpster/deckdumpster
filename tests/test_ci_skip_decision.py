"""The push-to-main skip decision fails closed (sp-fkhwo4)."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "ci_skip_decision", Path(__file__).resolve().parent.parent / "deploy/ci_skip_decision.py"
)
d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d)

REPO, PUSHED, HEAD, TREE = "o/r", "m1", "h1", "t1"


def _world(**over):
    w = {
        f"repos/{REPO}/commits/{PUSHED}": {"commit": {"tree": {"sha": TREE}}},
        f"repos/{REPO}/commits/{PUSHED}/pulls": [
            {"number": 7, "merged_at": "2026-10-11T00:00:00Z", "base": {"ref": "main"}, "head": {"sha": HEAD}}
        ],
        f"repos/{REPO}/commits/{HEAD}": {"commit": {"tree": {"sha": TREE}}},
        f"repos/{REPO}/actions/runs?head_sha={HEAD}&event=pull_request&status=success&per_page=100": {
            "workflow_runs": [
                {"id": 99, "path": d.WORKFLOW_PATH, "conclusion": "success", "head_sha": HEAD}
            ]
        },
        f"repos/{REPO}/pulls/7/files?per_page=100&page=1": [{"filename": "mtg_collector/x.py"}],
    }
    w.update(over)
    return w


def _decide(world, tiers=lambda files: d.FULL_TIERS):
    def api(path):
        v = world[path]
        if isinstance(v, Exception):
            raise v
        return v

    return d.decide(REPO, PUSHED, api=api, tiers_of=tiers)


def test_equal_tree_skips():
    skip, msg = _decide(_world())
    assert skip
    assert msg == "skipped: tree t1 already tested by PR #7 run 99"


def test_differing_tree_runs():
    skip, msg = _decide(_world(**{f"repos/{REPO}/commits/{HEAD}": {"commit": {"tree": {"sha": "other"}}}}))
    assert not skip and "differs" in msg


def test_no_pr_runs():
    skip, _ = _decide(_world(**{f"repos/{REPO}/commits/{PUSHED}/pulls": []}))
    assert not skip


def test_unmerged_pr_runs():
    pulls = [{"number": 7, "merged_at": None, "base": {"ref": "main"}, "head": {"sha": HEAD}}]
    skip, _ = _decide(_world(**{f"repos/{REPO}/commits/{PUSHED}/pulls": pulls}))
    assert not skip


def test_no_successful_run_runs():
    key = f"repos/{REPO}/actions/runs?head_sha={HEAD}&event=pull_request&status=success&per_page=100"
    skip, _ = _decide(_world(**{key: {"workflow_runs": []}}))
    assert not skip


def test_other_workflow_run_does_not_count():
    key = f"repos/{REPO}/actions/runs?head_sha={HEAD}&event=pull_request&status=success&per_page=100"
    other = {"id": 5, "path": ".github/workflows/x.yml", "conclusion": "success", "head_sha": HEAD}
    skip, _ = _decide(_world(**{key: {"workflow_runs": [other]}}))
    assert not skip


def test_reduced_tier_pr_run_runs():
    skip, msg = _decide(_world(), tiers=lambda files: "lint,unit")
    assert not skip and "lint,unit" in msg


@pytest.mark.parametrize("failing", [f"repos/{REPO}/commits/{PUSHED}", f"repos/{REPO}/commits/{PUSHED}/pulls", f"repos/{REPO}/commits/{HEAD}"])
def test_api_failure_runs(failing):
    skip, msg = _decide(_world(**{failing: RuntimeError("boom")}))
    assert not skip and "boom" in msg


def test_missing_response_key_runs():
    skip, _ = _decide(_world(**{f"repos/{REPO}/commits/{PUSHED}": {}}))
    assert not skip
