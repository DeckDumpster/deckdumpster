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
# The job that runs the suite. Its NAME is load-bearing, and since 2026-09-23 it
# is load-bearing for a DIFFERENT consumer than it used to be. Spira's merge
# queue reads a batch pull request's result through `forge.sh check-status`,
# which looks for a check named exactly `gate` and is hardcoded in two places
# with no configuration key. A missing `gate` check reads as PENDING FOREVER,
# so a batch pull request sits until SPIRA_QUEUE_CI_MAXSEC and then faults.
SUITE_JOB = "gate"

# main's `pr-required` ruleset requires a STATUS CHECK of this name. That is a
# separate thing from the job name above, and the two are allowed to differ
# because the suite job posts a commit status under this context explicitly --
# see test_the_required_check_is_posted. Before that step existed the job name
# WAS the check name, which is why renaming the job away from `test` once cost
# a merge (de-323).
REQUIRED_CONTEXT = "test"

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
    assert _gate_steps(SUITE_JOB) == ["bash deploy/ci.sh"]


def test_no_other_job_runs_a_gate():
    """The infrastructure jobs provision and destroy a machine. A gate that
    drifted into one of them would run outside deploy/ci.sh and could not be
    reproduced by hand at all."""
    for name in _jobs():
        if name == SUITE_JOB:
            continue
        assert _gate_steps(name) == [], f"{name} runs a gate outside deploy/ci.sh"


def test_the_script_exists_and_is_executable():
    assert CI_SCRIPT.exists()
    assert CI_SCRIPT.stat().st_mode & 0o111


def test_the_script_does_not_hardcode_an_instance_name():
    """Taking the runner's own `ci-test` by hand tears down a running CI job's
    container; the name has to stay overridable from the environment."""
    assert re.search(r'INSTANCE="\$\{INSTANCE:-[^}]+\}"', CI_SCRIPT.read_text())


def test_the_suite_job_exists_under_the_name_spira_reads():
    """Spira's merge queue finds the result by a check named exactly `gate`.

    `forge.sh check-status` does `next((c for c in checks if c["name"] ==
    "gate"), None)` and prints `pending` when that is None. Pending is not a
    failure, so nothing alerts: the batch pull request simply never settles."""
    assert SUITE_JOB in _jobs(), (
        f"no job named {SUITE_JOB!r}; Spira's queue will read every batch as pending"
    )


def test_the_required_check_is_posted():
    """main's `pr-required` ruleset requires a status check named `test`.

    GitHub does not fail a pull request whose required check never reports --
    it refuses the merge with "the base branch policy prohibits the merge"
    while every job in the run is green, so the workflow looks entirely
    healthy and the branch simply cannot land. Renaming the job away from
    `test` did exactly that and cost a merge (de-323).

    The job is now named `gate`, so the context is NOT supplied by the job
    name any more -- it is posted explicitly by a step inside that job. That
    step is therefore the only thing standing between a rename and a repository
    whose pull requests cannot merge, and this asserts it is still there and
    still unconditional. The ruleset is repository configuration and cannot be
    read from the tree; if it is ever changed, change REQUIRED_CONTEXT with it.
    """
    job = _jobs()[SUITE_JOB]
    posters = [
        step
        for step in job["steps"]
        if f'"context":"{REQUIRED_CONTEXT}"' in (step.get("run") or "")
    ]
    assert posters, (
        f"no step in {SUITE_JOB!r} posts a commit status with context "
        f"{REQUIRED_CONTEXT!r}; main's required check will never report"
    )
    assert all(step.get("if") == "always()" for step in posters), (
        f"the {REQUIRED_CONTEXT!r} status step must be `if: always()` -- a red "
        "run that posts nothing blocks the merge instead of failing it"
    )
