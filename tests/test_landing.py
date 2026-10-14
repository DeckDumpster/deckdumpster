"""Raw landing (lakehouse 3): manifests, content addressing, and the coverage audit."""

import json
import re
from pathlib import Path

from mtg_collector.landing import Run

ROOT = Path(__file__).resolve().parent.parent


def _manifest(run, source, dataset):
    part = run._partition(source, dataset)
    return json.loads((part / "_manifest.json").read_text())


def test_small_payload_lands_verbatim_with_manifest(tmp_path):
    run = Run(tmp_path)
    e = run.land_bytes(source="s", dataset="d", url="http://x/1", data=b"abc")
    assert (tmp_path / e["object"]).read_bytes() == b"abc"
    m = _manifest(run, "s", "d")
    assert m["run_id"] == run.run_id
    assert m["entries"][0]["url"] == "http://x/1"
    assert len(m["entries"][0]["sha256"]) == 64


def test_unchanged_bulk_content_lands_no_new_object(tmp_path):
    first = Run(tmp_path).land_bytes(source="s", dataset="d", url="u", data=b"big", bulk=True)
    run2 = Run(tmp_path)
    second = run2.land_bytes(source="s", dataset="d", url="u", data=b"big", bulk=True)
    assert first["deduplicated"] is False and second["deduplicated"] is True
    assert first["object"] == second["object"]
    assert len(list((tmp_path / "_objects").iterdir())) == 1
    assert _manifest(run2, "s", "d")["entries"][0]["object"] == first["object"]


def test_land_file_is_content_addressed(tmp_path):
    f = tmp_path / "dl.bin"
    f.write_bytes(b"payload")
    root = tmp_path / "raw"
    a = Run(root).land_file(source="s", dataset="d", url="u", path=f)
    b = Run(root).land_file(source="s", dataset="d", url="u", path=f)
    assert (a["deduplicated"], b["deduplicated"]) == (False, True)
    assert (root / a["object"]).read_bytes() == b"payload"


def test_every_upstream_fetch_is_landed():
    """Default-deny: a module that opens an upstream connection must name the landing module.

    `_api_shorten` posts a user-supplied URL to a link shortener; it fetches no
    upstream data and is the one deliberate exception.
    """
    fetchers = re.compile(r"urlopen\(|requests\.(get|post)\(|session\.(get|request)\(")
    exempt = {"mtg_collector/cli/crack_pack_server.py", "mtg_collector/landing.py"}
    offenders = []
    for path in (ROOT / "mtg_collector").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        text = path.read_text()
        if rel in exempt or not fetchers.search(text):
            continue
        if "landing import" not in text:
            offenders.append(rel)
    assert offenders == []


def test_refresh_unit_runs_in_its_own_container():
    unit = (ROOT / "deploy" / "mtgc-catalog-refresh.service").read_text()
    exec_line = [ln for ln in unit.splitlines() if ln.startswith("ExecStart=")][0]
    assert "podman run --rm" in exec_line and "podman exec" not in exec_line
    assert "MTGC_LAKE_RAW_DIR" in exec_line
