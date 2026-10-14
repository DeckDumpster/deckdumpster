"""Holdings outbox (lakehouse K4): atomicity, idempotence, rebuild == incremental."""

import sqlite3

import pytest

from mtg_collector.db.schema import init_db
from mtg_collector.lake import holdings_outbox as ho

FORBIDDEN = {"notes", "tags", "source_image", "order_id", "binder_id", "batch_id",
             "card_name", "source", "seller_name"}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = OFF")
    init_db(c)
    return c


def _card(c, pid="p1", finish="nonfoil", status="owned"):
    cur = c.execute(
        "INSERT INTO collection (printing_id, finish, acquired_at, source, status, notes) "
        "VALUES (?, ?, '2026-01-01T00:00:00.000Z', 'manual', ?, 'secret')",
        (pid, finish, status),
    )
    return cur.lastrowid


def _sealed(c, qty=1):
    return c.execute(
        "INSERT INTO sealed_collection (sealed_product_uuid, quantity, added_at) "
        "VALUES ('u1', ?, '2026-01-01')", (qty,)
    ).lastrowid


def test_insert_update_delete_each_emit(conn):
    i = _card(conn)
    conn.execute("UPDATE collection SET status = 'sold', sale_price = 3 WHERE id = ?", (i,))
    conn.execute("DELETE FROM collection WHERE id = ?", (i,))
    rows = conn.execute("SELECT source, row_id, op FROM holdings_outbox ORDER BY seq").fetchall()
    assert rows == [("collection", i, "upsert")] * 2 + [("collection", i, "delete")]


def test_unshipped_column_update_emits_nothing(conn):
    i = _card(conn)
    n = conn.execute("SELECT COUNT(*) FROM holdings_outbox").fetchone()[0]
    conn.execute("UPDATE collection SET notes = 'x', binder_id = NULL WHERE id = ?", (i,))
    assert conn.execute("SELECT COUNT(*) FROM holdings_outbox").fetchone()[0] == n


def test_rolled_back_mutation_leaves_no_outbox_row(conn):
    conn.commit()
    _card(conn)
    _sealed(conn)
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM holdings_outbox").fetchone()[0] == 0


def test_failed_statement_leaves_no_outbox_row(conn):
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO collection (printing_id, finish, acquired_at, source) "
            "VALUES ('p', 'bogus', 'x', 'manual')"
        )
    assert conn.execute("SELECT COUNT(*) FROM holdings_outbox").fetchone()[0] == 0


def test_only_holdings_columns_ship(conn):
    for src in ho.SOURCES:
        cols = set(ho.shipped_columns(conn, src))
        assert "id" in cols
        assert not cols & FORBIDDEN
        real = {r[1] for r in conn.execute(f"PRAGMA table_info({src})")}
        assert cols <= real
    _card(conn)
    p = conn.execute("SELECT payload FROM holdings_outbox").fetchone()[0]
    assert "secret" not in p


def test_update_and_insert_trigger_column_lists_agree(conn):
    for src in ho.SOURCES:
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?", (f"holdings_outbox_{src}_update",)
        ).fetchone()[0]
        listed = set(sql.split("UPDATE OF", 1)[1].split(" ON ")[0].replace(",", " ").split())
        assert listed | {"id"} == set(ho.shipped_columns(conn, src))


def test_rebuild_equals_incremental(conn):
    a, b = _card(conn), _card(conn, "p2", "foil")
    s = _sealed(conn)
    conn.execute("UPDATE collection SET status = 'sold' WHERE id = ?", (a,))
    conn.execute("UPDATE sealed_collection SET quantity = 4 WHERE id = ?", (s,))
    _card(conn, "p3")
    conn.execute("DELETE FROM collection WHERE id = ?", (b,))
    assert ho.fold(conn) == ho.current(conn)


def test_emit_backfills_rows_that_predate_the_triggers(conn):
    _card(conn)
    _sealed(conn)
    conn.execute("DELETE FROM holdings_outbox")
    assert ho.fold(conn) != ho.current(conn)
    assert ho.emit(conn) == 2
    assert ho.fold(conn) == ho.current(conn)


def test_emit_is_idempotent_in_effect(conn):
    _card(conn)
    _sealed(conn)
    ho.emit(conn)
    once = ho.fold(conn)
    ho.emit(conn)
    ho.emit(conn, "collection")
    assert ho.fold(conn) == once == ho.current(conn)


def test_emit_after_lost_log_recovers_deletes_of_nothing(conn):
    i = _card(conn)
    conn.execute("DELETE FROM holdings_outbox")
    conn.execute("DELETE FROM collection WHERE id = ?", (i,))
    ho.emit(conn)
    assert ho.fold(conn)["collection"] == {}


def test_migration_from_53_adds_outbox(conn):
    conn.executescript(
        "DROP TRIGGER holdings_outbox_collection_insert;"
        "DROP TRIGGER holdings_outbox_collection_update;"
        "DROP TRIGGER holdings_outbox_collection_delete;"
        "DROP TRIGGER holdings_outbox_sealed_collection_insert;"
        "DROP TRIGGER holdings_outbox_sealed_collection_update;"
        "DROP TRIGGER holdings_outbox_sealed_collection_delete;"
        "DROP TABLE holdings_outbox; DELETE FROM schema_version;"
        "INSERT INTO schema_version VALUES (53, 'x');"
    )
    assert init_db(conn)
    _card(conn)
    assert conn.execute("SELECT COUNT(*) FROM holdings_outbox").fetchone()[0] == 1
