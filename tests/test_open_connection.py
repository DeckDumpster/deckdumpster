"""The one connection opener: read-only shared attach, isolation, newer-schema refusal."""

import sqlite3

import pytest

from mtg_collector.db.connection import (
    IsolationError,
    SchemaTooNewError,
    assert_isolated,
    open_catalog_connection,
    open_connection,
)
from mtg_collector.db.schema import SCHEMA_VERSION, init_db


@pytest.fixture
def files(tmp_path):
    shared = tmp_path / "shared.sqlite"
    main = tmp_path / "tenant.sqlite"
    for p in (shared, main):
        c = sqlite3.connect(p)
        init_db(c)
        c.commit()
        c.close()
    c = sqlite3.connect(shared)
    c.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test')")
    c.commit()
    c.close()
    return str(main), str(shared)


def test_shared_is_attached_read_only(files):
    main, shared = files
    conn = open_connection(main, shared)
    assert conn.execute("SELECT set_name FROM sets").fetchone()[0] == "Test"
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO shared.sets (set_code, set_name) VALUES ('x', 'y')")


def test_assert_isolated_rejects_extra_attach(files, tmp_path):
    main, shared = files
    conn = open_connection(main, shared)
    conn.execute("ATTACH DATABASE ? AS other", (str(tmp_path / "other.sqlite"),))
    with pytest.raises(IsolationError):
        assert_isolated(conn, main, shared)


def test_refuses_newer_main(files):
    main, shared = files
    c = sqlite3.connect(main)
    c.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, 'x')", (SCHEMA_VERSION + 1,))
    c.commit()
    c.close()
    with pytest.raises(SchemaTooNewError):
        open_connection(main, shared)


def test_refuses_newer_shared(files):
    main, shared = files
    c = sqlite3.connect(shared)
    c.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, 'x')", (SCHEMA_VERSION + 1,))
    c.commit()
    c.close()
    with pytest.raises(SchemaTooNewError):
        open_connection(main, shared)


def test_catalog_connection_never_holds_the_tenant_file(files, monkeypatch):
    main, shared = files
    monkeypatch.setenv("MTGC_SHARED_DB", shared)
    conn = open_catalog_connection(main)
    paths = [r[2] for r in conn.execute("PRAGMA database_list") if r[1] != "temp"]
    assert paths == [shared] or [p.endswith("shared.sqlite") for p in paths] == [True]
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM sets")
