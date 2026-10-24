"""No deploy unit may name a path under /workspaces.

/workspaces is the harness checkout tree, not the product host's. A unit that
ExecStarts into it fails on every run, and a '-' prefix hides the failure
(sp-pck6yd: mtgc-alert@ carried a second ExecStart into the retired harness's
incident.sh).
"""

from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def test_there_are_units_to_check():
    assert list(DEPLOY.glob("*.service"))


def test_no_service_unit_references_workspaces():
    offenders = [
        f"{p.name}:{n}: {line.strip()}"
        for p in sorted(DEPLOY.glob("*.service"))
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if "/workspaces/" in line
    ]
    assert not offenders, "\n".join(offenders)
