import json
import sqlite3

import pytest

from mtg_collector.lake import zone_guard as g
from mtg_collector.lake.edhrec_fetchset import commander_fetch_set, commander_fetch_urls


def test_selftest_passes():
    g.selftest()


def test_guard_with_no_rules_would_fail_selftest(monkeypatch):
    monkeypatch.setattr(g, "check_zone", lambda **_: [])
    with pytest.raises(AssertionError):
        g.selftest()


@pytest.mark.parametrize("zone", [
    dict(tables={"prices": ["uuid", "tenant_id"]}),
    dict(urls=["https://x/y/01HZX3V5K8M2N4P6Q8R0S2T4V6"]),
    dict(manifests=[{"a": {"database_id": "x"}}]),
    dict(manifests=[{"a": ["ok", "tenant-7"]}]),
])
def test_each_surface_is_checked(zone):
    with pytest.raises(g.ZoneViolation):
        g.assert_clean(**zone)


def test_url_outside_catalog_set_is_flagged():
    assert g.check_urls(["https://a/b.json"], allowed={"https://a/c.json"})
    assert not g.check_urls(["https://a/b.json"], allowed={"https://a/b.json"})


def _catalog():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cards (oracle_id TEXT, name TEXT, type_line TEXT, oracle_text TEXT, legalities TEXT)")
    conn.execute("CREATE TABLE collection (printing_id TEXT, status TEXT)")
    legal = json.dumps({"commander": "legal"})
    conn.executemany("INSERT INTO cards VALUES (?,?,?,?,?)", [
        ("1", "Atraxa, Praetors' Voice", "Legendary Creature", "", legal),
        ("2", "Banned Guy", "Legendary Creature", "", json.dumps({"commander": "banned"})),
        ("3", "Bear", "Creature", "", legal),
        ("4", "Planeswalker Cmdr", "Legendary Planeswalker", "can be your commander", legal),
    ])
    return conn


def test_fetch_set_is_catalog_only_and_ignores_collection():
    conn = _catalog()
    before = commander_fetch_set(conn)
    conn.execute("INSERT INTO collection VALUES ('1', 'owned')")
    assert commander_fetch_set(conn) == before
    assert [n for n, _ in before] == ["Atraxa, Praetors' Voice", "Planeswalker Cmdr"]
    assert before[0][1] == "atraxa-praetors-voice"


def test_fetch_urls_pass_the_guard_against_themselves():
    conn = _catalog()
    urls = commander_fetch_urls(conn)
    g.assert_clean(urls=urls, allowed_urls=set(urls))
