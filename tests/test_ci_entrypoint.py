"""CI is one script (de-xz8).

The rig's agent instructions say `.github/workflows/ci.yml` runs
`bash deploy/ci.sh`, so anything not invoked from that script never runs in CI.
That was false for a while -- the file did not exist and the workflow carried a
dozen inline steps -- and it cost de-3a0 a session, which read the instruction,
found no such file, and stopped.

This asserts the shape the instruction describes, and deliberately asserts
nothing about which steps the script runs: enumerating them here would recreate
the second list that went stale in the first place.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
CI_SCRIPT = REPO_ROOT / "deploy/ci.sh"


def _run_steps():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    return [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "run" in step
    ]


def test_the_workflow_runs_exactly_one_command():
    """A second `run:` step is a gate that `bash deploy/ci.sh` does not
    reproduce, which is how the doc and the workflow drift apart."""
    assert _run_steps() == ["bash deploy/ci.sh"]


def test_the_script_exists_and_is_executable():
    assert CI_SCRIPT.exists()
    assert CI_SCRIPT.stat().st_mode & 0o111


def test_the_script_does_not_hardcode_an_instance_name():
    """Taking the runner's own `ci-test` by hand tears down a running CI job's
    container; the name has to stay overridable from the environment."""
    assert re.search(r'INSTANCE="\$\{INSTANCE:-[^}]+\}"', CI_SCRIPT.read_text())
