"""The binder card modal, and the condition that sticks for a whole pass.

Clicking the art in the binder grid opens `shared-card-modal.js` through its
`renderExtra` hook -- one `-/count/+` row per finish, plus a condition select
that is *not* per-card: the next pip click anywhere in the grid is filed under
it too, for the rest of the visit.  A binder is usually uniform, so re-picking
the condition per card is exactly the tax that makes a reconciliation pass not
worth doing.

Two halves have to meet:

  * `POST /api/collection` has to accept a `condition` at all.  It ignored one
    before this, so every copy the binder filed was Near Mint whatever the
    operator picked -- and an unrecognised value has to be a 400 rather than a
    coercion to the default, because silently filing a Lightly Played binder as
    Near Mint mislabels the lot.
  * The page has to send it, on the modal's steppers *and* on the pips.

The regression guard is `deck_builder.html`, the modal's other caller: it
passes no `renderExtra`, and nothing here may change what it sees.

To run: uv run pytest tests/test_binder_card_modal.py -v
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from mtg_collector.db.schema import init_db
from mtg_collector.utils import CONDITIONS

NOW = "2025-01-01T00:00:00.000Z"


@pytest.fixture
def db_path():
    """One printing in one set, nothing owned."""
    path = tempfile.mkstemp(suffix=".sqlite")[1]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO sets (set_code, set_name, released_at, cards_fetched_at)"
        " VALUES ('tst', 'Test Set', '2025-01-01', ?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO cards (oracle_id, name, type_line) VALUES ('oracle-1', 'Card 1', 'Creature')"
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number,"
        " rarity, finishes) VALUES ('print-1', 'oracle-1', 'tst', '1', 'R',"
        " '[\"nonfoil\", \"foil\"]')"
    )
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def _add(db_path, **payload):
    """POST /api/collection, returning (status, body)."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    responses = []
    handler._send_json = lambda obj, status=200: responses.append((status, obj))

    body = {"printing_id": "print-1", "finish": "nonfoil", "source": "binder"}
    body.update(payload)
    handler._api_collection_add(body)
    return responses[-1]


def _copies(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM collection ORDER BY id")]
    conn.close()
    return rows


class TestTheEndpointRecordsTheCondition:
    @pytest.mark.parametrize("condition", CONDITIONS)
    def test_every_condition_is_recorded_as_given(self, db_path, condition):
        status, body = _add(db_path, condition=condition)

        assert status == 200, body
        assert _copies(db_path)[0]["condition"] == condition

    def test_no_condition_is_near_mint(self, db_path):
        """The pips send one from the first click, but nothing else that posts
        here does, and a copy has to land in some condition."""
        status, body = _add(db_path)

        assert status == 200, body
        assert _copies(db_path)[0]["condition"] == "Near Mint"

    def test_an_unknown_condition_is_rejected(self, db_path):
        """A 400, not a coercion: the select sticks for a whole pass, so
        quietly downgrading it to the default would mislabel every copy of a
        binder rather than one."""
        status, body = _add(db_path, condition="Mint")

        assert status == 400
        assert "Mint" in body["error"]

    def test_a_rejected_condition_writes_nothing(self, db_path):
        _add(db_path, condition="Mint")

        assert _copies(db_path) == []

    def test_the_condition_travels_with_the_batch(self, db_path):
        """The two features are used together on every click of a pass, so the
        copy has to come out carrying both."""
        status, body = _add(
            db_path,
            condition="Lightly Played",
            batch={
                "batch_uuid": "11111111-2222-3333-4444-555555555555",
                "batch_type": "binder_click",
                "name": "Test Set binder",
                "set_code": "tst",
            },
        )

        assert status == 200, body
        copy = _copies(db_path)[0]
        assert copy["condition"] == "Lightly Played"
        assert copy["batch_id"] == body["batch_id"]


class TestTheMinusStepGivesTheBatchSlotBack:
    """The modal's `-` deletes the copy the `+` filed, and the batch it filed
    it under is the page's own audit trail -- `/batches` reads the stored
    `card_count`, so a counter that only ever went up would leave the review
    overstating a pass it exists to be trusted about."""

    def _spec(self):
        return {
            "batch_uuid": "11111111-2222-3333-4444-555555555555",
            "batch_type": "binder_click",
            "name": "Test Set binder",
            "set_code": "tst",
        }

    def _count(self, db_path, batch_id):
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT card_count FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
        conn.close()
        return row[0]

    def _delete(self, db_path, entry_id):
        from mtg_collector.cli.crack_pack_server import CrackPackHandler

        handler = object.__new__(CrackPackHandler)
        handler.db_path = db_path
        responses = []
        handler._send_json = lambda obj, status=200: responses.append((status, obj))
        handler._api_collection_delete(entry_id)
        return responses[-1]

    def test_deleting_a_filed_copy_decrements_its_batch(self, db_path):
        _, first = _add(db_path, batch=self._spec())
        _, second = _add(db_path, batch=self._spec())
        assert self._count(db_path, first["batch_id"]) == 2

        status, body = self._delete(db_path, second["id"])

        assert status == 200, body
        assert self._count(db_path, first["batch_id"]) == 1

    def test_the_count_matches_the_rows_that_are_left(self, db_path):
        _, first = _add(db_path, batch=self._spec())
        _add(db_path, batch=self._spec())
        self._delete(db_path, first["id"])

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT COUNT(*) FROM collection WHERE batch_id = ?", (first["batch_id"],)
        ).fetchone()[0]
        conn.close()

        assert self._count(db_path, first["batch_id"]) == rows

    def test_deleting_a_copy_in_no_batch_touches_no_batch(self, db_path):
        _, filed = _add(db_path, batch=self._spec())
        _, loose = _add(db_path)

        self._delete(db_path, loose["id"])

        assert self._count(db_path, filed["batch_id"]) == 1


def _static(name):
    from mtg_collector.cli import crack_pack_server as cps

    return (Path(cps.__file__).resolve().parent.parent / "static" / name).read_text()


class TestThePageSendsTheStickyCondition:
    """The endpoint files whatever condition it is given, so a page that stopped
    sending one would go on adding cards and quietly record them all as Near
    Mint."""

    def test_the_add_carries_the_condition(self):
        assert "condition: _condition," in _static("set_browse.html")

    def test_it_is_page_scope_not_per_card(self):
        """One variable for the whole visit is the entire feature: declared
        beside the page's other state, never reset when a card is opened."""
        js = _static("set_browse.html")

        assert "let _condition = CONDITIONS[0];" in js
        assert js.count("_condition =") == 2  # the declaration, and the select
        assert "if (e.target.id === 'binder-condition') _condition = e.target.value;" in js

    def test_the_pips_and_the_steppers_use_the_same_call(self):
        """A pip is `changeCopies(card, finish, +1)` and the modal's + is the
        same call, so there is one place the condition can be attached."""
        js = _static("set_browse.html")

        assert "changeCopies(tile._card, pip.dataset.finish, +1)" in js
        assert "changeCopies(_modalCard, btn.dataset.finish, Number(btn.dataset.delta))" in js

    def test_the_offered_conditions_are_the_ones_the_schema_accepts(self):
        """Offering a sixth would produce a 400 on click; offering five of six
        would make one unreachable from the binder."""
        js = _static("set_browse.html")

        listed = js.split("const CONDITIONS = [", 1)[1].split("];", 1)[0]
        assert [c for c in CONDITIONS if f"'{c}'" in listed] == list(CONDITIONS)


class TestTheModalIsTheSharedOneExtended:
    def test_it_is_opened_through_renderextra(self):
        assert "{renderExtra: renderBinderControls}" in _static("set_browse.html")

    def test_the_binder_does_not_fork_the_modal(self):
        """`createCardModal()` is called, never reimplemented."""
        js = _static("set_browse.html")

        assert "createCardModal()" in js
        assert "card-modal-overlay" not in js

    def test_one_stepper_row_per_finish(self):
        """Driven by `card.owned`, which carries an entry per finish the
        printing exists in -- including the empty ones, which are the pockets
        this page exists to fill."""
        js = _static("set_browse.html")

        rows = js.split("const rows = card.owned.map", 1)[1].split(".join('');", 1)[0]
        assert 'data-delta="-1"' in rows
        assert 'data-delta="1"' in rows
        assert 'class="binder-count"' in rows

    def test_the_foil_kind_is_a_badge_from_foil_kinds(self):
        """The third treatment axis, and a badge rather than a pip: `finishes`
        says a foil exists, `promo_types` says what kind it is, and you cannot
        own "surge"."""
        js = _static("set_browse.html")

        assert "parseJsonField(card.foil_kinds)" in js
        assert "badge foil-kind" in js
        assert "foilKindLabel(k)" in js

    def test_the_minus_step_names_the_copy_it_removes(self):
        """There is no "remove one copy of this printing" endpoint: a copy is a
        row with its own condition, price and history."""
        js = _static("set_browse.html")

        assert "/api/collection/copies?" in js
        assert "copies[0].id" in js
        assert "confirm=true" in js


class TestDeckBuilderIsUnaffected:
    """The real regression guard on this item: the modal already had a second
    caller before the binder existed, and its behaviour must not move."""

    def test_deck_builder_passes_no_render_extra(self):
        js = _static("deck-builder.js")

        assert "cardModal.show(zoneCards[idx]);" in js
        assert "renderExtra" not in js

    def test_the_hook_is_still_opt_in(self):
        """A caller that passes none gets the empty string it always got."""
        js = _static("shared-card-modal.js")

        assert "const extraHtml = opts.renderExtra ? opts.renderExtra(card) : '';" in js
