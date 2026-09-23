"""
Tests for db-fwn5: variation picker shows distinct cards instead of #1 #2 #3 #4.

All tests run at the unit tier (no container, no network).  The test fixture
(tests/fixtures/test-data.sqlite) carries J25's 121 decklists and FDN's 10.
"""

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

FIXTURE_DB = Path(__file__).parent / "fixtures" / "test-data.sqlite"


def _make_handler(db_path: str):
    """Minimal CrackPackHandler wired to an on-disk database."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler._responses = []

    def fake_send_json(obj, status=200):
        handler._responses.append((status, obj))

    handler._send_json = fake_send_json
    return handler


@pytest.fixture()
def fixture_db(tmp_path):
    """Read-only copy of the test fixture so tests don't mutate it."""
    dest = tmp_path / "test-data.sqlite"
    shutil.copy(FIXTURE_DB, dest)
    return str(dest)


def _call_precons_decks(handler, set_code: str, kind: str = "jumpstart") -> list:
    handler._api_precons_decks({"set_code": [set_code], "kind": [kind]})
    status, body = handler._responses[-1]
    assert status == 200, f"Expected 200, got {status}: {body}"
    return body


# ---------------------------------------------------------------------------
# Angels: 2-variation group — 4 named cards differ in each direction
# ---------------------------------------------------------------------------

class TestAngelsJ25:
    def test_two_variations_returned(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        angels = next(g for g in groups if g["base_name"] == "Angels")
        assert len(angels["variations"]) == 2

    def test_both_variations_have_non_empty_distinct(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        angels = next(g for g in groups if g["base_name"] == "Angels")
        for v in angels["variations"]:
            assert v.get("distinct"), f"{v['name']} has empty distinct list"

    def test_angels_1_distinct_cards(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        angels = next(g for g in groups if g["base_name"] == "Angels")
        v1 = next(v for v in angels["variations"] if v["variation"] == 1)
        assert set(v1["distinct"]) == {
            "Celestial Enforcer", "Destroy Evil", "Light of Hope", "Serra Angel"
        }

    def test_angels_2_distinct_cards(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        angels = next(g for g in groups if g["base_name"] == "Angels")
        v2 = next(v for v in angels["variations"] if v["variation"] == 2)
        assert set(v2["distinct"]) == {
            "Angelic Edict", "Herald of War", "Rally of Wings", "Stalwart Valkyrie"
        }

    def test_distinct_lists_are_disjoint(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        angels = next(g for g in groups if g["base_name"] == "Angels")
        v1_set = set(angels["variations"][0]["distinct"])
        v2_set = set(angels["variations"][1]["distinct"])
        assert v1_set.isdisjoint(v2_set), "distinct lists must not overlap"

    def test_deck_data_not_leaked(self, fixture_db):
        """_deck_data temp key must not appear in the response."""
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        for g in groups:
            for v in g["variations"]:
                assert "_deck_data" not in v


# ---------------------------------------------------------------------------
# Armed: 4-variation group — each variation has a non-empty distinct list,
# and no variation is diffed against variation 1 alone.
# ---------------------------------------------------------------------------

class TestArmedJ25:
    def _armed_variations(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        return next(g for g in groups if g["base_name"] == "Armed")["variations"]

    def test_four_variations_returned(self, fixture_db):
        assert len(self._armed_variations(fixture_db)) == 4

    def test_all_four_have_non_empty_distinct(self, fixture_db):
        for v in self._armed_variations(fixture_db):
            assert v.get("distinct"), f"{v['name']} has empty distinct list"

    def test_distinct_not_computed_against_variation_1_only(self, fixture_db):
        """A card shared between variations 1 and 3 must still appear in variation 3's
        distinct list when it is absent from at least one other sibling.

        Pairwise-against-variation-1 would fail this: if a card is present in both (1)
        and (3), diffing (3) against only (1) yields no difference for that card, so it
        disappears from (3)'s list.  The correct algorithm ('absent from at least one
        sibling') keeps it.

        Armed j25: Valkyrie's Sword is in Armed (1) and Armed (3) but not in Armed (2)
        or Armed (4), so it must appear in Armed (3)'s distinct list.
        """
        variations = self._armed_variations(fixture_db)
        v3 = next(v for v in variations if v["variation"] == 3)
        distinct_names = {
            label.split("× ", 1)[-1] if "× " in label else label
            for label in v3["distinct"]
        }
        assert "Valkyrie's Sword" in distinct_names, (
            "Valkyrie's Sword is in Armed (1) and Armed (3) but absent from (2) and (4); "
            "it must appear in Armed (3)'s distinct list (pairwise-against-1 would miss it)"
        )

    def test_each_distinct_card_absent_from_at_least_one_sibling(self, fixture_db):
        """Verify the definition: every listed card is missing from at least one sibling."""
        conn = sqlite3.connect(fixture_db)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT name, deck_data FROM mtgjson_decks WHERE base_name = 'Armed' AND set_code = 'j25' ORDER BY variation"
        ).fetchall()

        all_uuids = set()
        for r in rows:
            for e in json.loads(r["deck_data"]).get("mainBoard", []):
                all_uuids.add(e["uuid"])
        ph = ",".join("?" * len(all_uuids))
        uuid_to_name = {
            row["uuid"]: row["name"]
            for row in conn.execute(
                f"""SELECT m.uuid, c.name FROM mtgjson_uuid_map m
                    JOIN printings p ON p.set_code = m.set_code
                                    AND p.collector_number = m.collector_number
                    JOIN cards c ON c.oracle_id = p.oracle_id
                    WHERE m.uuid IN ({ph})""",
                list(all_uuids),
            ).fetchall()
        }
        conn.close()

        # Build aggregated card sets per variation.
        var_cards = []
        for r in rows:
            counts: dict = {}
            for e in json.loads(r["deck_data"]).get("mainBoard", []):
                name = uuid_to_name.get(e["uuid"])
                if name:
                    counts[name] = counts.get(name, 0) + e.get("count", 1)
            var_cards.append(counts)

        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        armed = next(g for g in groups if g["base_name"] == "Armed")

        for i, v in enumerate(armed["variations"]):
            for label in v["distinct"]:
                name = label.split("× ", 1)[-1] if "× " in label else label
                count = var_cards[i].get(name, 0)
                absent_from_some_sibling = any(
                    var_cards[j].get(name, 0) != count
                    for j in range(len(var_cards)) if j != i
                )
                assert absent_from_some_sibling, (
                    f"'{name}' in {v['name']} distinct list is present "
                    "at the same count in all siblings — should be in the common set"
                )


# ---------------------------------------------------------------------------
# Land count difference: a group whose variations differ only in land quantity
# must produce a non-empty distinct list with the count shown.
# ---------------------------------------------------------------------------

class TestLandCountDifference:
    def test_drowned_island_count_in_distinct(self, fixture_db):
        """Drowned (j25) variations differ by one Island; counts must show."""
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        drowned = next(g for g in groups if g["base_name"] == "Drowned")
        assert len(drowned["variations"]) == 2

        # Both lists should contain an Island entry with a count prefix.
        island_labels = []
        for v in drowned["variations"]:
            for label in v["distinct"]:
                if label.endswith("Island"):
                    island_labels.append(label)

        assert len(island_labels) == 2, "Expected one Island entry per variation"
        assert island_labels[0] != island_labels[1], "Island counts must differ between variations"
        for label in island_labels:
            assert "× Island" in label, f"Expected 'N× Island', got: {label!r}"


# ---------------------------------------------------------------------------
# Synthetic land-count-only test: a minimal constructed DB where the ONLY
# difference between two variations is 6 Mountain vs 5 Mountain.
# ---------------------------------------------------------------------------

class TestSyntheticCountOnlyDifference:
    @pytest.fixture()
    def count_only_db(self, tmp_path):
        """Two variations that share every card but differ in Mountain count."""
        db_path = str(tmp_path / "count_only.sqlite")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        from mtg_collector.db.schema import init_db
        init_db(conn)

        conn.executescript("""
            INSERT OR IGNORE INTO sets (set_code, set_name, digital) VALUES ('tst', 'Test', 0);
            INSERT OR IGNORE INTO cards (oracle_id, name) VALUES ('o-bolt', 'Lightning Bolt');
            INSERT OR IGNORE INTO cards (oracle_id, name) VALUES ('o-mtn', 'Mountain');
        """)
        conn.execute(
            "INSERT OR IGNORE INTO printings (printing_id, oracle_id, set_code, collector_number) VALUES ('p-bolt', 'o-bolt', 'tst', '1')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO printings (printing_id, oracle_id, set_code, collector_number) VALUES ('p-mtn', 'o-mtn', 'tst', '2')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO mtgjson_uuid_map (uuid, set_code, collector_number) VALUES ('uuid-bolt', 'tst', '1')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO mtgjson_uuid_map (uuid, set_code, collector_number) VALUES ('uuid-mtn', 'tst', '2')"
        )

        deck_v1 = json.dumps({
            "mainBoard": [
                {"uuid": "uuid-bolt", "count": 2},
                {"uuid": "uuid-mtn", "count": 6},
            ]
        })
        deck_v2 = json.dumps({
            "mainBoard": [
                {"uuid": "uuid-bolt", "count": 2},
                {"uuid": "uuid-mtn", "count": 5},
            ]
        })
        conn.execute(
            """INSERT INTO mtgjson_decks (set_code, name, base_name, variation, type, main_count, deck_data)
               VALUES ('tst', 'Burn (1)', 'Burn', 1, 'Jumpstart', 8, ?)""",
            (deck_v1,),
        )
        conn.execute(
            """INSERT INTO mtgjson_decks (set_code, name, base_name, variation, type, main_count, deck_data)
               VALUES ('tst', 'Burn (2)', 'Burn', 2, 'Jumpstart', 7, ?)""",
            (deck_v2,),
        )
        conn.commit()
        conn.close()
        return db_path

    def test_distinct_non_empty_for_count_only_diff(self, count_only_db):
        handler = _make_handler(count_only_db)
        groups = _call_precons_decks(handler, "tst")
        burn = next(g for g in groups if g["base_name"] == "Burn")
        v1 = next(v for v in burn["variations"] if v["variation"] == 1)
        v2 = next(v for v in burn["variations"] if v["variation"] == 2)
        assert v1["distinct"], "Variation 1 should have non-empty distinct list"
        assert v2["distinct"], "Variation 2 should have non-empty distinct list"

    def test_mountain_count_shown_in_label(self, count_only_db):
        handler = _make_handler(count_only_db)
        groups = _call_precons_decks(handler, "tst")
        burn = next(g for g in groups if g["base_name"] == "Burn")
        v1 = next(v for v in burn["variations"] if v["variation"] == 1)
        v2 = next(v for v in burn["variations"] if v["variation"] == 2)
        # Mountain is the only distinguishing card, and it appears in both —
        # so the count must appear in the label.
        assert any("6" in label and "Mountain" in label for label in v1["distinct"]), (
            f"Expected '6× Mountain' in v1 distinct, got: {v1['distinct']}"
        )
        assert any("5" in label and "Mountain" in label for label in v2["distinct"]), (
            f"Expected '5× Mountain' in v2 distinct, got: {v2['distinct']}"
        )

    def test_bolt_not_in_distinct(self, count_only_db):
        """Lightning Bolt is identical in both variations — must not be in distinct."""
        handler = _make_handler(count_only_db)
        groups = _call_precons_decks(handler, "tst")
        burn = next(g for g in groups if g["base_name"] == "Burn")
        for v in burn["variations"]:
            assert not any("Bolt" in label for label in v["distinct"]), (
                f"Lightning Bolt should not appear in distinct: {v['distinct']}"
            )


# ---------------------------------------------------------------------------
# FDN single-variation: the variation key is absent, picker stays hidden.
# ---------------------------------------------------------------------------

class TestFdnSingleVariation:
    def test_single_variation_has_no_distinct_key(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "fdn")
        cats = next(g for g in groups if g["base_name"] == "Cats")
        assert len(cats["variations"]) == 1
        assert "distinct" not in cats["variations"][0], (
            "Single-variation groups must not carry a distinct key"
        )

    def test_fdn_no_groups_have_distinct_key(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "fdn")
        for g in groups:
            for v in g["variations"]:
                assert "distinct" not in v, (
                    f"FDN has no multi-variation themes; {g['base_name']} should not have distinct"
                )


# ---------------------------------------------------------------------------
# Payload shape: distinct is names/labels, not full printing objects.
# ---------------------------------------------------------------------------

class TestPayloadShape:
    def test_distinct_contains_only_strings(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        for g in groups:
            for v in g["variations"]:
                for item in v.get("distinct", []):
                    assert isinstance(item, str), (
                        f"distinct items must be strings, got {type(item)}: {item!r}"
                    )

    def test_no_printing_objects_in_distinct(self, fixture_db):
        handler = _make_handler(fixture_db)
        groups = _call_precons_decks(handler, "j25")
        for g in groups:
            for v in g["variations"]:
                for item in v.get("distinct", []):
                    assert not isinstance(item, dict), (
                        "distinct must not contain printing/card objects"
                    )
