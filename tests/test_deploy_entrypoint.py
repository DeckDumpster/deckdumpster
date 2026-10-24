"""A job unit that runs a CLI command in the mtgc image must override the entrypoint.

The image's ENTRYPOINT is the web server, so `podman run ... mtgc:prod mtg data
derive` appends the job to `mtg crack-pack-server --port 8081 --https` and dies
with "unrecognized arguments". Every lakehouse chain unit did that and failed
nightly (sp-svtd9b). The convention is `--entrypoint mtg` with the subcommand
after the image.
"""

import re
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
FILES = sorted(DEPLOY.glob("*.service")) + [DEPLOY / "lake-drill.sh"]
IMAGE_THEN_MTG = re.compile(r"mtgc:\S+\s+mtg\s|\$IMAGE\"?\s+mtg\s")


def _offenders():
    out = []
    for f in FILES:
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if IMAGE_THEN_MTG.search(line) or (
                "podman run" in line and "mtgc:" in line and "--entrypoint" not in line
                and f.suffix == ".service"
            ):
                out.append(f"{f.name}:{n}")
    return out


def test_no_job_runs_the_server_entrypoint():
    assert _offenders() == []


@pytest.mark.parametrize("f", [f for f in FILES if f.suffix == ".service"], ids=lambda f: f.name)
def test_every_service_podman_run_overrides_entrypoint(f):
    for line in f.read_text().splitlines():
        if "podman run" in line and "mtgc:" in line:
            assert "--entrypoint mtg " in line, line[:80]
