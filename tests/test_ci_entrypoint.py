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


def _jobs():
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]


def _run_steps(job_name=None):
    jobs = _jobs()
    chosen = jobs.values() if job_name is None else [jobs[job_name]]
    return [step["run"] for job in chosen for step in job["steps"] if "run" in step]


# What counts as a gate: anything that exercises the repository rather than
# preparing the machine to. Matched by what it runs, not by an allowlist of
# step names -- an allowlist is the second list this module exists to prevent.
GATE = re.compile(r"\bpytest\b|\bruff\b|\buv run\b|deploy/ci\.sh")


def _gate_steps(job_name=None):
    return [s for s in _run_steps(job_name) if GATE.search(s)]


def test_the_test_job_runs_exactly_one_gate():
    """A second gate in the workflow is one `bash deploy/ci.sh` does not
    reproduce, which is how the doc and the workflow drift apart.

    Scoped to the job that runs the suite. When this was written the workflow
    had one job, so "every run: step" and "every gate" were the same sentence.
    CI now provisions an ephemeral VM and destroys it afterwards (de-323), and
    those jobs legitimately run commands -- cloning a VM, minting a runner
    token, tearing it down. None of them validates the repository, and holding
    them to "exactly one command" would only mean asserting a list of them
    here.

    Machine setup inside the test job is not a gate either, and deliberately
    does not weaken the guarantee: deploy/ci.sh calls
    `runner-deps.sh --check` itself, so running it by hand still reproduces
    the dependency requirement rather than trusting the workflow to have met
    it."""
    assert _gate_steps("ci") == ["bash deploy/ci.sh"]


def test_no_other_job_runs_a_gate():
    """The infrastructure jobs provision and destroy a machine. A gate that
    drifted into one of them would run outside deploy/ci.sh and could not be
    reproduced by hand at all."""
    for name in _jobs():
        if name == "ci":
            continue
        assert _gate_steps(name) == [], f"{name} runs a gate outside deploy/ci.sh"


def test_the_script_exists_and_is_executable():
    assert CI_SCRIPT.exists()
    assert CI_SCRIPT.stat().st_mode & 0o111


def test_the_script_does_not_hardcode_an_instance_name():
    """Taking the runner's own `ci-test` by hand tears down a running CI job's
    container; the name has to stay overridable from the environment."""
    assert re.search(r'INSTANCE="\$\{INSTANCE:-[^}]+\}"', CI_SCRIPT.read_text())
