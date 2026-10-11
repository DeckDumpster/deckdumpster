"""Decide whether a push to main may skip the suite (sp-fkhwo4).

A push to main is almost always the exact tree its batch pull request just
passed; re-running the suite there adds flake exposure and holds the repo-wide
CI slot, not coverage. This answers one question -- "was this tree already
tested, in full, by a successful run of this workflow?" -- and fails closed:
every doubt (no PR, no run, differing tree, reduced tiers, API error) is a
decision to run the full suite.

stdlib only; the `gh` CLI is the single I/O seam (`gh_api`), injectable for tests.
"""

import json
import os
import subprocess
import sys

WORKFLOW_PATH = ".github/workflows/ci.yml"
FULL_TIERS = "lint,unit,integration,ui"
COMPUTE_TIERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compute-tiers.sh")


def gh_api(path):
    out = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=True, timeout=120
    ).stdout
    return json.loads(out)


def compute_tiers(files):
    return subprocess.run(
        ["bash", COMPUTE_TIERS],
        input="\n".join(files) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()


def _pr_files(api, repo, number):
    files, page = [], 1
    while True:
        batch = api(f"repos/{repo}/pulls/{number}/files?per_page=100&page={page}")
        files += [f["filename"] for f in batch]
        if len(batch) < 100:
            return files
        page += 1


def decide(repo, sha, api=gh_api, tiers_of=compute_tiers, base="main"):
    """Return (skip, message). Never raises: any failure is (False, reason)."""
    try:
        return _decide(repo, sha, api, tiers_of, base)
    except Exception as e:  # fail closed: doubt runs the suite
        return False, f"run: could not decide ({type(e).__name__}: {e})"


def _decide(repo, sha, api, tiers_of, base):
    tree = api(f"repos/{repo}/commits/{sha}")["commit"]["tree"]["sha"]

    prs = [
        p
        for p in api(f"repos/{repo}/commits/{sha}/pulls")
        if p.get("merged_at") and p["base"]["ref"] == base
    ]
    if len(prs) != 1:
        return False, f"run: {len(prs)} merged PRs found for {sha}, need exactly 1"
    pr = prs[0]
    number, head = pr["number"], pr["head"]["sha"]

    head_tree = api(f"repos/{repo}/commits/{head}")["commit"]["tree"]["sha"]
    if head_tree != tree:
        return False, f"run: PR #{number} head tree {head_tree} differs from pushed tree {tree}"

    runs = api(
        f"repos/{repo}/actions/runs?head_sha={head}&event=pull_request&status=success&per_page=100"
    )["workflow_runs"]
    runs = [
        r
        for r in runs
        if r.get("path") == WORKFLOW_PATH
        and r.get("conclusion") == "success"
        and r.get("head_sha") == head
    ]
    if not runs:
        return False, f"run: no successful CI run for PR #{number} head {head}"
    run = max(runs, key=lambda r: r["id"])

    tiers = tiers_of(_pr_files(api, repo, number))
    if tiers != FULL_TIERS:
        return False, f"run: PR #{number} run {run['id']} only covered tiers {tiers}"

    return True, f"skipped: tree {tree} already tested by PR #{number} run {run['id']}"


def main():
    event, repo, sha = os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    if event != "push":
        skip, msg = False, f"run: {event} always runs the full suite"
    else:
        skip, msg = decide(repo, sha)
    print(msg)
    with open(os.environ["GITHUB_OUTPUT"], "a") as out:
        out.write(f"skip={'true' if skip else 'false'}\nmessage={msg}\n")


if __name__ == "__main__":
    sys.exit(main())
