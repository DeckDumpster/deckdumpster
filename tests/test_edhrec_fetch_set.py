"""K3: the EDHREC fetch set is a function of the catalog only."""
import sqlite3

from mtg_collector.cli.data_cmd import edhrec_fetch_set

CARDS = [
    ("o1", "Alpha Legend", "Legendary Creature — Elf", None, '{"commander": "legal"}'),
    ("o2", "Beta Legend", "Legendary Creature — Elf", None, '{"commander": "legal"}'),
    ("o3", "Banned Legend", "Legendary Creature — Elf", None, '{"commander": "banned"}'),
    ("o4", "Plain Bear", "Creature — Bear", None, '{"commander": "legal"}'),
    ("o5", "Walker", "Legendary Planeswalker", "X can be your commander.", '{"commander": "legal"}'),
]


def _db(with_tenant_rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE cards (oracle_id TEXT PRIMARY KEY, name TEXT, type_line TEXT,"
                 " oracle_text TEXT, legalities TEXT)")
    conn.executemany(
        "INSERT INTO cards (oracle_id, name, type_line, oracle_text, legalities)"
        " VALUES (?,?,?,?,?)", CARDS)
    if with_tenant_rows:
        conn.execute("CREATE TABLE collection (printing_id TEXT, status TEXT)")
        conn.execute("INSERT INTO collection VALUES ('o1', 'owned')")
    return conn


def test_fetch_set_is_every_legal_commander():
    names = [r["name"] for r in edhrec_fetch_set(_db(False))]
    assert names == ["Alpha Legend", "Beta Legend", "Walker"]


def test_no_tenant_row_influences_the_fetch_set():
    bare = [tuple(r) for r in edhrec_fetch_set(_db(False))]
    held = [tuple(r) for r in edhrec_fetch_set(_db(True))]
    assert bare == held


def test_fetch_set_runs_without_any_tenant_table():
    # a catalog-only connection has no collection table at all
    assert edhrec_fetch_set(_db(False))
