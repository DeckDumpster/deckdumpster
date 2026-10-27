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

    Deliberate exceptions, none of which fetches catalog or price data:
    `_api_shorten` posts a user-supplied URL to a link shortener, and
    `access.py` fetches Cloudflare Access's signing keys to verify a login.
    """
    fetchers = re.compile(r"urlopen\(|requests\.(get|post)\(|session\.(get|request)\(")
    exempt = {"mtg_collector/cli/crack_pack_server.py", "mtg_collector/access.py",
              "mtg_collector/landing.py"}
    offenders = []
    for path in (ROOT / "mtg_collector").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        text = path.read_text()
        if rel in exempt or not fetchers.search(text):
            continue
        if "landing import" not in text:
            offenders.append(rel)
    assert offenders == []


def test_land_unit_runs_in_its_own_container():
    unit = (ROOT / "deploy" / "mtgc-land.service").read_text()
    exec_line = [ln for ln in unit.splitlines() if ln.startswith("ExecStart=")][0]
    assert "podman run --rm" in exec_line and "podman exec" not in exec_line
    assert "MTGC_LAKE_RAW_DIR" in exec_line


def test_a_landed_manifest_passes_the_catalog_zone_guard(tmp_path):
    """The guard's manifest and URL surfaces are checked against what landing
    really writes, not a hand-built dict; the planted tenant URL is the positive
    control that the same read goes red."""
    from mtg_collector.lake import zone_guard as g

    run = Run(tmp_path)
    url = "https://json.edhrec.com/pages/commanders/atraxa-praetors-voice.json"
    run.land_bytes(source="edhrec", dataset="commanders", url=url, data=b"{}")
    path = run._partition("edhrec", "commanders") / "_manifest.json"
    manifest = json.loads(path.read_text())
    g.assert_clean(manifests=[manifest], urls=[e["url"] for e in manifest["entries"]])

    run.land_bytes(source="edhrec", dataset="commanders",
                   url="https://x/01HZX3V5K8M2N4P6Q8R0S2T4V6.json", data=b"{}")
    planted = json.loads(path.read_text())
    try:
        g.assert_clean(manifests=[planted])
    except g.ZoneViolation:
        return
    raise AssertionError("a tenant-shaped URL in a landed manifest was not flagged")


def test_a_failed_set_page_fails_the_land_instead_of_landing_short(monkeypatch):
    """A set page that errors must stop the land: swallowed, the run lands
    'successfully' without it and the derive then dies on a ReplayMiss (sp-46n53b)."""
    import pytest
    import requests

    from mtg_collector.services import bulk_import

    class Boom:
        headers: dict = {}

        def update(self, *_):
            pass

        def request(self, *a, **k):
            raise requests.exceptions.ConnectionError("down")

    client = bulk_import.ScryfallBulkClient()
    client.session = Boom()
    monkeypatch.setattr(client, "_rate_limit", lambda: None)
    with pytest.raises(RuntimeError, match="4ed"):
        client.get_set_cards("4ed")
    with pytest.raises(RuntimeError, match="4ed"):
        client.get_set_cards_all_langs("4ed")
