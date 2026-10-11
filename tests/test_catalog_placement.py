"""Catalog placement: a tenant file never holds the catalogue (sp-y8iflb)."""

import ast
import hashlib
import sqlite3
from pathlib import Path

import pytest

from mtg_collector.db.connection import open_connection
from mtg_collector.db.schema import (
    REGISTRY_SCHEMA_SQL,
    SCHEMA_OBJECTS,
    SHARED_TABLES,
    SHARED_VIEWS,
    SHARED_VIRTUAL,
    init_db,
    rebuild_fts,
)
from mtg_collector.db import tenants

CATALOG = set(SHARED_TABLES) | set(SHARED_VIEWS) | set(SHARED_VIRTUAL)


def _names(path):
    c = sqlite3.connect(path)
    try:
        return {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
    finally:
        c.close()


@pytest.fixture
def pair(tmp_path):
    shared = str(tmp_path / "shared.sqlite")
    tenant = str(tmp_path / "tenant.sqlite")
    c = sqlite3.connect(shared)
    init_db(c)
    c.execute("INSERT INTO cards (oracle_id, name, type_line, oracle_text) "
              "VALUES ('o1', 'Lightning Bolt', 'Instant', 'Deal 3 damage')")
    rebuild_fts(c)
    c.commit()
    c.close()
    # A tenant is created through a connection that carries the catalogue.
    t = open_connection(tenant, shared)
    init_db(t)
    t.commit()
    t.close()
    return tenant, shared


def test_tenant_file_holds_no_catalog_object(pair):
    tenant, shared = pair
    assert not (_names(tenant) & CATALOG)
    assert "collection" in _names(tenant)


def test_shared_file_holds_the_catalog_and_fts(pair):
    _, shared = pair
    assert CATALOG <= _names(shared)


def test_every_schema_object_is_in_user_or_shared():
    from mtg_collector.db.schema import SHARED_SCHEMA_SQL, USER_SCHEMA_SQL, _CREATE_RE

    user = set(_CREATE_RE.findall(USER_SCHEMA_SQL))
    shared = set(_CREATE_RE.findall(SHARED_SCHEMA_SQL))
    assert not user & shared
    assert user | shared == SCHEMA_OBJECTS


def test_fts_search_through_a_tenant_connection(pair):
    """cards_fts resolves by name to the shared copy; results match the catalogue's own."""
    tenant, shared = pair
    t = open_connection(tenant, shared)
    got = [r[0] for r in t.execute(
        "SELECT rowid FROM cards_fts WHERE cards_fts MATCH 'damage'")]
    t.close()
    s = sqlite3.connect(shared)
    want = [r[0] for r in s.execute(
        "SELECT rowid FROM cards_fts WHERE cards_fts MATCH 'damage'")]
    s.close()
    assert got == want and len(got) == 1


def test_tenant_bytes_unchanged_by_a_catalog_refresh(pair):
    """A catalog refresh leaves every tenant file byte-identical."""
    tenant, shared = pair
    digest = lambda: hashlib.sha256(Path(tenant).read_bytes()).hexdigest()
    before = digest()
    s = sqlite3.connect(shared)
    s.execute("INSERT INTO cards (oracle_id, name, type_line, oracle_text) "
              "VALUES ('o2', 'Counterspell', 'Instant', 'Counter target spell')")
    rebuild_fts(s)
    s.commit()
    s.close()
    assert digest() == before
    assert not Path(tenant + "-wal").exists() or Path(tenant + "-wal").stat().st_size == 0


def test_tenant_bytes_positive_control(pair):
    """The check can see a leak: writing the tenant file changes its digest."""
    tenant, _ = pair
    before = hashlib.sha256(Path(tenant).read_bytes()).hexdigest()
    c = sqlite3.connect(tenant)
    c.execute("INSERT INTO settings (key, value) VALUES ('x', 'y')")
    c.commit()
    c.close()
    assert hashlib.sha256(Path(tenant).read_bytes()).hexdigest() != before


# ── N8: no request handler writes the catalogue ──

_CATALOG_WRITERS = {
    "_fetch_prices", "fetch_sealed_prices", "import_prices", "import_mtgjson",
    "import_sealed_products", "fetch_edhrec", "import_edhrec", "backfill_sets",
    "refresh_catalog", "fetch_allprintings", "rebuild_fts", "rebuild_card_names",
    "get_shared_write_path", "rebuild_collection_card_names", "cache_all", "cache_set",
}
_SERVER = Path(__file__).parent.parent / "mtg_collector/cli/crack_pack_server.py"


def _referenced_names(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            yield n.id
        elif isinstance(n, ast.Attribute):
            yield n.attr
        elif isinstance(n, ast.alias):
            yield n.name


def test_no_request_handler_opens_the_catalog_for_writing():
    tree = ast.parse(_SERVER.read_text())
    assert not _CATALOG_WRITERS & set(_referenced_names(tree))


def test_the_catalog_write_routes_are_gone():
    src = _SERVER.read_text()
    assert '"/api/fetch-prices"' not in src
    assert '"/api/sealed/fetch-prices"' not in src


def test_guard_positive_control():
    tree = ast.parse("from x import fetch_sealed_prices\nfetch_sealed_prices(1)")
    assert _CATALOG_WRITERS & set(_referenced_names(tree))


# ── D8: the offline per-tenant growth job ──


def test_growth_walks_the_registry_and_reports_partial(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    reg = sqlite3.connect(tmp_path / "registry.sqlite")
    reg.executescript(REGISTRY_SCHEMA_SQL)
    ids = ["01HZZZZZZZZZZZZZZZZZZZZZZA", "01HZZZZZZZZZZZZZZZZZZZZZZB", "01HZZZZZZZZZZZZZZZZZZZZZZC"]
    for h, i in zip("abc", ids):
        reg.execute("INSERT INTO user (handle, database_id, created_at) VALUES (?, ?, 'now')", (h, i))
    reg.execute("UPDATE user SET retired_at = 'now' WHERE handle = 'c'")
    reg.commit()
    reg.close()
    assert [l for l, _ in tenants.list_tenants("unused")] == ids[:2]

    seen = []

    def open_tenant(path):
        if path.endswith(ids[0] + ".sqlite"):
            raise RuntimeError("corrupt")
        seen.append(path)
        return sqlite3.connect(":memory:")

    code = tenants.rebuild_growth_all(
        "unused", rebuild=lambda c: 7, open_tenant=open_tenant)
    out = capsys.readouterr().out
    assert code == tenants.PARTIAL_EXIT
    assert len(seen) == 1 and seen[0].endswith(ids[1] + ".sqlite")
    assert "PARTIAL" in out and ids[0] in out


def test_registry_rules():
    c = sqlite3.connect(":memory:")
    c.executescript(REGISTRY_SCHEMA_SQL)
    ins = "INSERT INTO user (handle, database_id, created_at) VALUES (?, ?, 'now')"
    c.execute(ins, ("ann", "01HZZZZZZZZZZZZZZZZZZZZZZA"))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(ins, ("ann", "01HZZZZZZZZZZZZZZZZZZZZZZB"))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(ins, ("Bob", "01HZZZZZZZZZZZZZZZZZZZZZZC"))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(ins, ("bob", "01hzzzzzzzzzzzzzzzzzzzzzzc"))


def test_single_tenant_mode_is_the_configured_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    assert tenants.list_tenants("/x/collection.sqlite") == [("single", "/x/collection.sqlite")]
