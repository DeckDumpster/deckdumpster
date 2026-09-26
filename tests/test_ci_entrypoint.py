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
import subprocess
from pathlib import Path

import yaml

from tests.subprocess_run import DEFAULT_TIMEOUT

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"
CI_SCRIPT = REPO_ROOT / "deploy/ci.sh"
COMPUTE_TIERS = REPO_ROOT / "deploy/compute-tiers.sh"


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


def _run_compute_tiers(files: list[str]) -> str:
    """Run deploy/compute-tiers.sh with the given file list and return output."""
    result = subprocess.run(
        ["bash", str(COMPUTE_TIERS)],
        input="\n".join(files) + ("\n" if files else ""),
        capture_output=True,
        text=True,
        check=True,
        timeout=DEFAULT_TIMEOUT,
    )
    return result.stdout.strip()


def test_compute_tiers_full_suite_for_unknown_path():
    """An unrecognised path must select every tier, never a subset.

    A selector that narrows on an unfamiliar path is how a real regression
    ships undetected: the change lands in an unrecognised location, only
    lint+unit runs, and the integration gap is never caught (db-5sku)."""
    assert _run_compute_tiers(["mtg_collector/server.py"]) == "lint,unit,integration,ui"


def test_compute_tiers_cheap_for_workflow_only():
    """A diff touching only workflow files and this test file selects lint+unit."""
    files = [".github/workflows/ci.yml", "tests/test_ci_entrypoint.py"]
    assert _run_compute_tiers(files) == "lint,unit"


def test_compute_tiers_full_suite_for_mixed_diff():
    """Cheap + unrecognised → full suite. One unknown file is enough."""
    files = [".github/workflows/ci.yml", "mtg_collector/server.py"]
    assert _run_compute_tiers(files) == "lint,unit,integration,ui"


def test_compute_tiers_full_suite_for_empty_input():
    """No changed files → full suite. Empty input cannot be narrowed safely."""
    assert _run_compute_tiers([]) == "lint,unit,integration,ui"


def test_compute_tiers_cheap_for_markdown():
    """A diff touching only a top-level Markdown file selects lint+unit."""
    assert _run_compute_tiers(["README.md"]) == "lint,unit"


def test_compute_tiers_cheap_for_docs():
    """A diff touching only files under docs/ selects lint+unit."""
    assert _run_compute_tiers(["docs/some-guide.md"]) == "lint,unit"


def test_compute_tiers_cheap_for_gitignore():
    """A diff touching only .gitignore selects lint+unit."""
    assert _run_compute_tiers([".gitignore"]) == "lint,unit"


def test_compute_tiers_cheap_for_license():
    """A diff touching only LICENSE selects lint+unit."""
    assert _run_compute_tiers(["LICENSE"]) == "lint,unit"


def test_compute_tiers_full_suite_for_tests_md():
    """A Markdown file under tests/ must NOT read as cheap.

    A file at tests/fixtures/card-list.md or similar could be test input.
    A pattern that treated it as documentation would let a fixture change
    skip the suite that reads it."""
    assert _run_compute_tiers(["tests/fixtures/some-fixture.md"]) == "lint,unit,integration,ui"


def test_run_ci_step_passes_tiers_env():
    """The Run CI step passes DECKDUMP_CI_TIERS from the tiers step's output.

    Without this, ci.sh never learns which tiers to skip and always runs
    everything regardless of what compute-tiers selected."""
    steps = {
        s.get("name"): s
        for job in _jobs().values()
        for s in job.get("steps", [])
        if "name" in s
    }
    run_ci = steps.get("Run CI", {})
    env = run_ci.get("env", {})
    assert "DECKDUMP_CI_TIERS" in env, (
        "Run CI step must pass DECKDUMP_CI_TIERS so ci.sh respects tier selection"
    )
