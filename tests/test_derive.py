"""The offline derive is row-identical to the inline build (lakehouse 4).

The inline build runs the refresh with the network stubbed to a fixture upstream,
landing every byte. The derive then rebuilds a second database from that landed
run alone, with the network made to raise. The two catalogues must match row for
row; `derive` is `refresh_catalog` reading a replay, so a divergence means the
replay layer changed a byte.
"""

import gzip
import json
import sqlite3

import pytest
import requests

from mtg_collector.cli import data_cmd
from mtg_collector.landing import Replay, ReplayMiss, Run, reset_run

BULK_URI = "https://data.scryfall.io/default-cards/default-cards-1.jsonl.gz"
CARDS = [
    {"id": "scry-1", "oracle_id": "or-1", "name": "Plains", "set": "tst",
     "collector_number": "1", "rarity": "common", "lang": "en", "type_line": "Basic Land",
     "cmc": 0, "colors": [], "color_identity": ["W"], "keywords": [], "legalities": {},
     "finishes": ["nonfoil"], "image_uris": {"normal": "https://img/1"}},
    {"id": "scry-2", "oracle_id": "or-2", "name": "Island", "set": "tst",
     "collector_number": "2", "rarity": "common", "lang": "en", "type_line": "Basic Land",
     "cmc": 0, "colors": [], "color_identity": ["U"], "keywords": [], "legalities": {},
     "finishes": ["nonfoil", "foil"], "image_uris": {"normal": "https://img/2"}},
]
ALLPRINTINGS = {"data": {"TST": {"name": "Test Set", "cards": [
    {"uuid": "u-1", "name": "Plains", "number": "1", "setCode": "tst", "rarity": "common",
     "borderColor": "black", "isFullArt": False, "identifiers": {"scryfallId": "scry-1"},
     "purchaseUrls": {"cardKingdom": "https://ck.com/plains"}},
    {"uuid": "u-2", "name": "Island", "number": "2", "setCode": "tst", "rarity": "common",
     "borderColor": "black", "isFullArt": False, "identifiers": {"scryfallId": "scry-2"},
     "purchaseUrls": {}},
]}}}

BODIES = {
    "https://api.scryfall.com/sets": json.dumps({"object": "list", "data": [
        {"code": "tst", "name": "Test Set", "set_type": "core", "released_at": "2020-01-01",
         "digital": False, "card_count": 2}]}).encode(),
    "https://api.scryfall.com/bulk-data": json.dumps({"object": "list", "data": [
        {"type": "default_cards", "jsonl_download_uri": BULK_URI}]}).encode(),
    BULK_URI: gzip.compress("".join(json.dumps(c) + "\n" for c in CARDS).encode()),
    "https://mtgjson.com/api/v5/AllPrintings.json.gz": gzip.compress(json.dumps(ALLPRINTINGS).encode()),
    "https://mtgjson.com/api/v5/Meta.json": json.dumps({"data": {"version": "5.2.2+test"}}).encode(),
}


class _Resp:
    status_code = 200
    headers = {}

    def __init__(self, url):
        self.url = url
        self.content = BODIES[url]

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=0):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Urlopen:
    def __init__(self, req, timeout=None):
        self._body = BODIES[req.full_url]

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    # copyfileobj reads in chunks
    def readinto(self, b):  # pragma: no cover
        raise NotImplementedError


def _no_network(*a, **kw):
    raise AssertionError("the derive reached for the network")


def _dump(db):
    conn = sqlite3.connect(db)
    out = {}
    for t in ("cards", "printings", "sets", "mtgjson_printings", "mtgjson_uuid_map", "settings"):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})") if r[1] not in ("imported_at", "updated_at", "cached_at", "cards_fetched_at")]
        out[t] = sorted(conn.execute(f"SELECT {', '.join(cols)} FROM {t}").fetchall(), key=repr)
    conn.close()
    return out


@pytest.fixture
def partition(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    monkeypatch.setenv("MTGC_LAKE_RAW_DIR", str(raw))
    monkeypatch.setenv("MTGC_HOME", str(tmp_path / "inline-home"))
    monkeypatch.setattr(requests.Session, "request", lambda self, m, url, params=None, **kw: _Resp(
        requests.Request(m, url, params=params).prepare().url))
    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kw: _Resp(url))
    import shutil
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Urlopen(req, timeout))
    real_copy = shutil.copyfileobj
    monkeypatch.setattr(shutil, "copyfileobj", lambda src, dst, *a: dst.write(src.read()) if isinstance(src, _Urlopen) else real_copy(src, dst, *a))
    reset_run()
    inline_db = str(tmp_path / "inline.sqlite")
    data_cmd.refresh_catalog(inline_db)
    reset_run()
    return raw, inline_db


def test_derive_is_row_identical_to_the_inline_build(partition, tmp_path, monkeypatch):
    raw, inline_db = partition
    monkeypatch.setattr(requests.Session, "request", _no_network)
    monkeypatch.setattr(requests.Session, "get", _no_network)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", _no_network)
    monkeypatch.setenv("MTGC_HOME", str(tmp_path / "derive-home"))
    derived_db = str(tmp_path / "derived.sqlite")
    data_cmd.derive_catalog(derived_db, raw_root=str(raw))
    reset_run()
    a, b = _dump(inline_db), _dump(derived_db)
    assert a["printings"] and a["mtgjson_printings"]
    assert a == b


def test_derive_writes_no_raw_byte(partition, tmp_path, monkeypatch):
    raw, _ = partition
    before = sorted(p.relative_to(raw) for p in raw.rglob("*"))
    monkeypatch.setenv("MTGC_HOME", str(tmp_path / "derive-home"))
    data_cmd.derive_catalog(str(tmp_path / "d.sqlite"), raw_root=str(raw))
    reset_run()
    assert before == sorted(p.relative_to(raw) for p in raw.rglob("*"))


def test_a_url_the_run_never_landed_is_a_miss_not_a_fetch(tmp_path):
    run = Run(tmp_path)
    run.land_bytes(source="s", dataset="d", url="http://x/1", data=b"a")
    replay = Replay(tmp_path)
    assert replay.fetch("http://x/1") == b"a"
    with pytest.raises(ReplayMiss):
        replay.fetch("http://x/2")


def test_the_newest_run_is_the_one_replayed(tmp_path):
    old = Run(tmp_path)
    old.land_bytes(source="s", dataset="d", url="u", data=b"old")
    new = Run(tmp_path)
    new.run_id = "Z" * 26
    new.land_bytes(source="s", dataset="d", url="u", data=b"new")
    assert Replay(tmp_path).fetch("u") == b"new"
    assert Replay(tmp_path, old.run_id).fetch("u") == b"old"


def test_an_empty_root_is_a_miss(tmp_path):
    with pytest.raises(ReplayMiss):
        Replay(tmp_path)
