"""The binder grid's lazy session batch.

One click on a finish pip adds one copy, and every add of a page visit is
filed under a single `binder_click` batch so the pass is reviewable at
`/batches/:id` afterwards.  The batch is created by the FIRST add that carries
its uuid, which is what lets browsing — which posts nothing — leave no batch
behind, and what makes a second add join the first rather than open another.

Every assertion here fails against `_api_collection_add` as it was: it ignored
a `batch` entirely and filed every copy under no batch at all.

To run: uv run pytest tests/test_binder_session_batch.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.models import Batch, BatchRepository
from mtg_collector.db.schema import init_db

NOW = "2025-01-01T00:00:00.000Z"
UUID = "11111111-2222-3333-4444-555555555555"


def _spec(**kw):
    """The descriptor set_browse.html sends on every pip add."""
    spec = {
        "batch_uuid": UUID,
        "batch_type": "binder_click",
        "name": "Test Set binder",
        "set_code": "tst",
    }
    spec.update(kw)
    return spec


@pytest.fixture
def db_path():
    """Two printings in one set, nothing owned."""
    path = tempfile.mkstemp(suffix=".sqlite")[1]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO sets (set_code, set_name, released_at, cards_fetched_at)"
        " VALUES ('tst', 'Test Set', '2025-01-01', ?)",
        (NOW,),
    )
    for n in (1, 2):
        conn.execute(
            "INSERT INTO cards (oracle_id, name, type_line) VALUES (?, ?, 'Creature')",
            (f"oracle-{n}", f"Card {n}"),
        )
        conn.execute(
            "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number,"
            " rarity, finishes) VALUES (?, ?, 'tst', ?, 'R', '[\"nonfoil\", \"foil\"]')",
            (f"print-{n}", f"oracle-{n}", str(n)),
        )
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def _add(db_path, printing_id="print-1", finish="nonfoil", batch=None):
    """POST /api/collection, returning (status, body)."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    responses = []
    handler._send_json = lambda obj, status=200: responses.append((status, obj))

    payload = {"printing_id": printing_id, "finish": finish, "source": "binder"}
    if batch is not None:
        payload["batch"] = batch
    handler._api_collection_add(payload)
    return responses[-1]


def _batches(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM batches ORDER BY id")]
    conn.close()
    return rows


def _copies(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM collection ORDER BY id")]
    conn.close()
    return rows


class TestTheFirstAddCreatesTheBatch:
    def test_one_add_creates_exactly_one_batch(self, db_path):
        status, body = _add(db_path, batch=_spec())

        assert status == 200, body
        batches = _batches(db_path)
        assert len(batches) == 1
        assert batches[0]["id"] == body["batch_id"]

    def test_the_batch_is_named_for_the_set_and_typed_binder_click(self, db_path):
        _add(db_path, batch=_spec())

        batch = _batches(db_path)[0]

        assert batch["batch_type"] == "binder_click"
        assert batch["name"] == "Test Set binder"
        assert batch["set_code"] == "tst"

    def test_the_copy_is_filed_under_it(self, db_path):
        _, body = _add(db_path, batch=_spec())

        copies = _copies(db_path)

        assert len(copies) == 1
        assert copies[0]["batch_id"] == body["batch_id"]

    def test_the_batch_lists_and_shows_its_card(self, db_path):
        """`/batches/:id` reads through BatchRepository, so the pass is
        reviewable afterwards — the point of filing an optimistic add at all."""
        _, body = _add(db_path, batch=_spec())

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        repo = BatchRepository(conn)
        batch = repo.get(body["batch_id"])
        cards = repo.get_cards(body["batch_id"])
        listed = repo.list_all()
        conn.close()

        assert batch["card_count"] == 1
        assert [c["printing_id"] for c in cards] == ["print-1"]
        assert [b["id"] for b in listed] == [body["batch_id"]]


class TestLaterAddsJoinIt:
    """The whole point of the uuid: a binder pass is one batch, not one per
    click."""

    def test_a_second_add_creates_no_second_batch(self, db_path):
        _, first = _add(db_path, "print-1", batch=_spec())
        _, second = _add(db_path, "print-2", batch=_spec())

        assert second["batch_id"] == first["batch_id"]
        assert len(_batches(db_path)) == 1

    def test_every_copy_of_the_pass_is_in_it(self, db_path):
        _add(db_path, "print-1", "nonfoil", batch=_spec())
        _add(db_path, "print-1", "foil", batch=_spec())
        _add(db_path, "print-2", "nonfoil", batch=_spec())

        batch = _batches(db_path)[0]

        assert batch["card_count"] == 3
        assert {c["batch_id"] for c in _copies(db_path)} == {batch["id"]}

    def test_a_later_add_does_not_rename_the_batch(self, db_path):
        """The batch was described when it was created; a join is not a
        rename, so a stale name on a later request cannot rewrite it."""
        _add(db_path, "print-1", batch=_spec())

        _add(db_path, "print-2", batch=_spec(name="TST binder"))

        assert _batches(db_path)[0]["name"] == "Test Set binder"

    def test_a_new_visit_gets_its_own_batch(self, db_path):
        """A fresh page visit mints a fresh uuid, so yesterday's pass is not
        reopened by today's."""
        _, first = _add(db_path, "print-1", batch=_spec())

        _, second = _add(db_path, "print-2", batch=_spec(batch_uuid="other-uuid"))

        assert second["batch_id"] != first["batch_id"]
        assert len(_batches(db_path)) == 2


class TestNoBatchIsCreatedWithoutAnAdd:
    def test_an_add_with_no_batch_files_under_none(self, db_path):
        """Every other caller of this endpoint sends no batch and must keep
        behaving exactly as it did."""
        status, body = _add(db_path)

        assert status == 200, body
        assert "batch_id" not in body
        assert _batches(db_path) == []
        assert _copies(db_path)[0]["batch_id"] is None

    @pytest.mark.parametrize("missing", ["batch_uuid", "batch_type"])
    def test_a_batch_without_its_identity_is_rejected(self, db_path, missing):
        """Not a silent default: an add filed under a nameless or untyped
        batch would land on the schema's 'corner' default and mislabel the
        copy forever."""
        status, body = _add(db_path, batch=_spec(**{missing: ""}))

        assert status == 400
        assert missing in body["error"]

    def test_a_rejected_add_writes_nothing_at_all(self, db_path):
        _add(db_path, batch=_spec(batch_uuid=""))

        assert _batches(db_path) == []
        assert _copies(db_path) == []


class TestGetOrCreate:
    """The repository primitive, on its own: identity is the uuid."""

    def _repo(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn, BatchRepository(conn)

    def test_the_same_uuid_twice_is_one_row(self, db_path):
        conn, repo = self._repo(db_path)

        first = repo.get_or_create(Batch(id=None, batch_uuid=UUID, batch_type="binder_click"))
        second = repo.get_or_create(Batch(id=None, batch_uuid=UUID, batch_type="binder_click"))
        conn.commit()
        conn.close()

        assert first == second
        assert len(_batches(db_path)) == 1

    def test_a_racing_first_add_takes_the_winners_row(self, db_path):
        """The server is threaded and a binder pass is a run of clicks, so two
        adds can both read no batch before either has written one. The loser's
        INSERT then waits on the winner's write lock, wakes to a committed row
        and violates UNIQUE(batch_uuid); it has to take that row rather than
        500 the add. Keying on the uuid is only worth anything if a fast pass
        cannot open two batches.

        The stale read is injected rather than raced for: the ordering is real
        but a threaded test of it would be timing-dependent, and this is the
        branch that has to work when it happens.
        """
        conn, repo = self._repo(db_path)
        won = repo.get_or_create(Batch(id=None, batch_uuid=UUID, batch_type="binder_click"))
        conn.commit()

        real_get_by_uuid = repo.get_by_uuid
        stale = [True]

        def one_stale_read(batch_uuid):
            """The read the loser made before the winner committed."""
            if stale:
                stale.pop()
                return None
            return real_get_by_uuid(batch_uuid)

        repo.get_by_uuid = one_stale_read

        lost = repo.get_or_create(Batch(id=None, batch_uuid=UUID, batch_type="binder_click"))
        conn.commit()
        conn.close()

        assert lost == won
        assert len(_batches(db_path)) == 1

    def test_a_different_uuid_is_a_different_row(self, db_path):
        conn, repo = self._repo(db_path)

        first = repo.get_or_create(Batch(id=None, batch_uuid=UUID, batch_type="binder_click"))
        second = repo.get_or_create(Batch(id=None, batch_uuid="b", batch_type="binder_click"))
        conn.commit()
        conn.close()

        assert first != second
        assert len(_batches(db_path)) == 2


class TestThePageSendsOne:
    """The two halves have to meet: the endpoint files a copy under a batch
    only when the request carries one, so a page that stopped sending it would
    keep adding cards and quietly stop recording the pass."""

    def _js(self):
        from pathlib import Path

        from mtg_collector.cli import crack_pack_server as cps

        static = Path(cps.__file__).resolve().parent.parent / "static"
        return (static / "set_browse.html").read_text()

    def test_the_add_carries_the_session_batch(self):
        assert "batch: sessionBatch()" in self._js()

    def test_the_uuid_is_minted_on_the_first_add_and_reused(self):
        """`sessionBatch()` is the only place a uuid is made, and it makes one
        only when it has none — mint per call and every click would open its
        own batch."""
        js = self._js()

        assert js.count("crypto.randomUUID()") == 1
        assert "if (!_batchUuid) _batchUuid = crypto.randomUUID();" in js

    def test_the_batch_is_typed_and_named_for_the_set(self):
        js = self._js()

        assert "batch_type: 'binder_click'," in js
        assert "set_code: SET_CODE," in js
