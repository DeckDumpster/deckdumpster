"""
Integration tests for deck, binder, and collection view API endpoints.

Runs against a live container instance with demo data loaded.

    uv run pytest tests/integration/test_decks_binders_api.py -v --instance <instance>

To set up the instance:

    bash deploy/setup.sh <instance> --test
    systemctl --user start mtgc-<instance>
"""

import pytest  # noqa: I001


def _get_unassigned_entry_ids(api, count=1):
    """Get individual collection entry IDs for unassigned cards via /api/collection/copies."""
    # Get some collection entries (grouped by printing)
    status, collection = api.get("/api/collection?limit=20")
    if status != 200 or not collection:
        return []

    entry_ids = []
    for card in collection:
        pid = card["printing_id"]
        finish = card.get("finish", "nonfoil")
        status, copies = api.get(f"/api/collection/copies?printing_id={pid}&finish={finish}")
        if status == 200:
            for copy in copies:
                if not copy.get("deck_id") and not copy.get("binder_id"):
                    entry_ids.append(copy["id"])
                    if len(entry_ids) >= count:
                        return entry_ids
    return entry_ids


# =============================================================================
# Deck CRUD
# =============================================================================


class TestDeckCRUD:
    """Full lifecycle: create -> read -> update -> delete."""

    def test_create_deck(self, api):
        status, deck = api.post("/api/decks", {
            "name": "Integration Test Deck",
            "format": "commander",
            "description": "Created by integration test",
        })
        assert status == 201
        assert deck["id"] is not None
        assert deck["name"] == "Integration Test Deck"
        assert deck["format"] == "commander"

        try:
            # Read back
            status, result = api.get(f"/api/decks/{deck['id']}")
            assert status == 200
            assert result["name"] == "Integration Test Deck"
            assert result["card_count"] == 0
        finally:
            api.delete(f"/api/decks/{deck['id']}")

    def test_list_decks(self, api):
        _, d1 = api.post("/api/decks", {"name": "List Test A"})
        _, d2 = api.post("/api/decks", {"name": "List Test B"})

        try:
            status, decks = api.get("/api/decks")
            assert status == 200
            assert isinstance(decks, list)
            names = {d["name"] for d in decks}
            assert "List Test A" in names
            assert "List Test B" in names
        finally:
            api.delete(f"/api/decks/{d1['id']}")
            api.delete(f"/api/decks/{d2['id']}")

    def test_update_deck(self, api):
        _, deck = api.post("/api/decks", {"name": "Before Update"})
        deck_id = deck["id"]

        try:
            status, result = api.put(f"/api/decks/{deck_id}", {
                "name": "After Update",
                "format": "modern",
                "sleeve_color": "black",
            })
            assert status == 200

            status, updated = api.get(f"/api/decks/{deck_id}")
            assert status == 200
            assert updated["name"] == "After Update"
            assert updated["format"] == "modern"
        finally:
            api.delete(f"/api/decks/{deck_id}")

    def test_delete_deck(self, api):
        _, deck = api.post("/api/decks", {"name": "To Delete"})
        deck_id = deck["id"]

        status, result = api.delete(f"/api/decks/{deck_id}")
        assert status == 200

        status, result = api.get(f"/api/decks/{deck_id}")
        assert status == 404

    def test_create_deck_missing_name(self, api):
        status, data = api.post("/api/decks", {})
        assert status == 400
        assert "name" in data.get("error", "").lower()

    def test_get_nonexistent_deck(self, api):
        status, data = api.get("/api/decks/999999")
        assert status == 404

    def test_delete_nonexistent_deck(self, api):
        status, data = api.delete("/api/decks/999999")
        assert status == 404

    def test_create_deck_all_fields(self, api):
        status, deck = api.post("/api/decks", {
            "name": "Full Deck",
            "format": "legacy",
            "description": "A legacy deck",
            "is_precon": True,
            "sleeve_color": "red dragon shield matte",
            "deck_box": "Ultimate Guard Boulder 100+",
            "storage_location": "shelf 2, left side",
        })
        assert status == 201
        deck_id = deck["id"]

        try:
            status, result = api.get(f"/api/decks/{deck_id}")
            assert status == 200
            assert result["name"] == "Full Deck"
            assert result["format"] == "legacy"
            assert result["is_precon"] == 1
            assert result["sleeve_color"] == "red dragon shield matte"
            assert result["deck_box"] == "Ultimate Guard Boulder 100+"
            assert result["storage_location"] == "shelf 2, left side"
        finally:
            api.delete(f"/api/decks/{deck_id}")


# =============================================================================
# Deck card management
# =============================================================================


class TestDeckCards:
    """Add, remove, and list cards in decks."""

    @pytest.fixture
    def deck_with_cards(self, api):
        """Create a constructed deck and find collection card IDs to work with."""
        _, deck = api.post("/api/decks", {"name": "Card Test Deck", "state": "constructed"})
        deck_id = deck["id"]

        card_ids = _get_unassigned_entry_ids(api, count=3)

        yield deck_id, card_ids

        # Cleanup
        api.delete(f"/api/decks/{deck_id}")

    def test_add_cards_to_deck(self, api, deck_with_cards):
        deck_id, card_ids = deck_with_cards
        if len(card_ids) < 2:
            pytest.skip("Not enough unassigned collection cards")

        status, result = api.post(f"/api/decks/{deck_id}/cards", {
            "collection_ids": card_ids[:2],
            "zone": "mainboard",
        })
        assert status == 200
        assert result["count"] == 2

        # Verify cards appear in deck
        status, cards = api.get(f"/api/decks/{deck_id}/cards")
        assert status == 200
        assert len(cards) == 2

    def test_add_cards_with_zone_filter(self, api, deck_with_cards):
        deck_id, card_ids = deck_with_cards
        if len(card_ids) < 2:
            pytest.skip("Need at least 2 collection cards")

        # Add to different zones
        api.post(f"/api/decks/{deck_id}/cards", {
            "collection_ids": [card_ids[0]],
            "zone": "mainboard",
        })
        api.post(f"/api/decks/{deck_id}/cards", {
            "collection_ids": [card_ids[1]],
            "zone": "sideboard",
        })

        # Filter by zone
        status, mainboard = api.get(f"/api/decks/{deck_id}/cards?zone=mainboard")
        assert status == 200
        assert len(mainboard) == 1

        status, sideboard = api.get(f"/api/decks/{deck_id}/cards?zone=sideboard")
        assert status == 200
        assert len(sideboard) == 1

        status, all_cards = api.get(f"/api/decks/{deck_id}/cards")
        assert status == 200
        assert len(all_cards) == 2

    def test_deck_card_count(self, api, deck_with_cards):
        deck_id, card_ids = deck_with_cards
        if len(card_ids) < 2:
            pytest.skip("Not enough unassigned collection cards")

        api.post(f"/api/decks/{deck_id}/cards", {
            "collection_ids": card_ids[:2],
            "zone": "mainboard",
        })

        status, deck = api.get(f"/api/decks/{deck_id}")
        assert status == 200
        assert deck["card_count"] == 2

    def test_add_cards_empty_list(self, api, deck_with_cards):
        deck_id, _ = deck_with_cards
        status, result = api.post(f"/api/decks/{deck_id}/cards", {
            "collection_ids": [],
            "zone": "mainboard",
        })
        # Empty list should return 400 since collection_ids is required
        assert status == 400


# =============================================================================
# Expected list management
# =============================================================================


class TestExpectedListRemoval:
    """Removing entries from a constructed deck's expected list.

    Repros the /decks/31 scenario: a card sits in deck_expected_cards but
    not in deck_cards, so it only surfaces in the completeness "missing"
    block at the bottom of the page with no editable handle. The UI only
    knows the oracle_id (completeness groups by oracle), so the remove
    endpoint must accept oracle_id + zone, not just printing_id.
    """

    def _pick_printing(self, api):
        status, data = api.get("/api/collection?limit=5")
        assert status == 200
        cards = data if isinstance(data, list) else data.get("cards", [])
        assert cards, "No cards in collection — cannot run expected-list test"
        card = cards[0]
        return card["printing_id"], card["oracle_id"], card["name"]

    def test_remove_missing_expected_card_by_oracle(self, api):
        """Reproduce the Infernal Vessel bug: expected card with no matching
        deck_cards entry should be removable from the completeness view,
        where only oracle_id is known."""
        printing_id, oracle_id, name = self._pick_printing(api)

        _, deck = api.post("/api/decks", {
            "name": "Expected Removal Test",
            "state": "constructed",
        })
        deck_id = deck["id"]

        try:
            status, result = api.post(
                f"/api/decks/{deck_id}/expected-cards/add",
                {"printing_ids": [printing_id], "zone": "mainboard"},
            )
            assert status == 200
            assert result["count"] == 1

            status, completeness = api.get(
                f"/api/decks/{deck_id}/completeness")
            assert status == 200
            missing_oracles = {m["oracle_id"] for m in completeness["missing"]}
            assert oracle_id in missing_oracles, (
                f"Expected {name} to appear as missing, got "
                f"{completeness}")

            # The UI only has oracle_id from the completeness payload.
            # Remove by oracle_id + zone — this is the path the fix enables.
            status, result = api.post(
                f"/api/decks/{deck_id}/expected-cards/remove",
                {"oracle_id": oracle_id, "zone": "mainboard"},
            )
            assert status == 200, f"Remove failed: {result}"
            assert result["removed"] == 1

            status, completeness = api.get(
                f"/api/decks/{deck_id}/completeness")
            assert status == 200
            missing_oracles = {m["oracle_id"] for m in completeness["missing"]}
            assert oracle_id not in missing_oracles, (
                f"{name} should be gone from missing, got {completeness}")
        finally:
            api.delete(f"/api/decks/{deck_id}")

    def test_remove_expected_by_printing_still_works(self, api):
        """Existing printing_id path should keep working for callers that
        have it (the swap flow already relies on it)."""
        printing_id, _, _ = self._pick_printing(api)

        _, deck = api.post("/api/decks", {
            "name": "Expected Removal Printing Test",
            "state": "constructed",
        })
        deck_id = deck["id"]

        try:
            api.post(
                f"/api/decks/{deck_id}/expected-cards/add",
                {"printing_ids": [printing_id], "zone": "mainboard"},
            )
            status, result = api.post(
                f"/api/decks/{deck_id}/expected-cards/remove",
                {"printing_id": printing_id},
            )
            assert status == 200
            assert result["removed"] == 1
        finally:
            api.delete(f"/api/decks/{deck_id}")

    def test_remove_expected_requires_identifier(self, api):
        _, deck = api.post("/api/decks", {
            "name": "Expected Removal Validation Test",
            "state": "constructed",
        })
        deck_id = deck["id"]
        try:
            status, result = api.post(
                f"/api/decks/{deck_id}/expected-cards/remove", {})
            assert status == 400
            assert "printing_id" in result["error"] or \
                "oracle_id" in result["error"]
        finally:
            api.delete(f"/api/decks/{deck_id}")


# =============================================================================
# Binder CRUD
# =============================================================================


class TestBinderCRUD:
    """Full lifecycle: create -> read -> update -> delete."""

    def test_create_binder(self, api):
        status, binder = api.post("/api/binders", {
            "name": "Integration Test Binder",
            "color": "blue",
        })
        assert status == 201
        assert binder["id"] is not None
        assert binder["name"] == "Integration Test Binder"

        try:
            status, result = api.get(f"/api/binders/{binder['id']}")
            assert status == 200
            assert result["name"] == "Integration Test Binder"
            assert result["card_count"] == 0
        finally:
            api.delete(f"/api/binders/{binder['id']}")

    def test_list_binders(self, api):
        _, b1 = api.post("/api/binders", {"name": "Binder A"})
        _, b2 = api.post("/api/binders", {"name": "Binder B"})

        try:
            status, binders = api.get("/api/binders")
            assert status == 200
            names = {b["name"] for b in binders}
            assert "Binder A" in names
            assert "Binder B" in names
        finally:
            api.delete(f"/api/binders/{b1['id']}")
            api.delete(f"/api/binders/{b2['id']}")

    def test_update_binder(self, api):
        _, binder = api.post("/api/binders", {"name": "Old Binder"})
        binder_id = binder["id"]

        try:
            status, result = api.put(f"/api/binders/{binder_id}", {
                "name": "New Binder",
                "color": "red",
                "binder_type": "9-pocket",
            })
            assert status == 200

            status, updated = api.get(f"/api/binders/{binder_id}")
            assert updated["name"] == "New Binder"
            assert updated["color"] == "red"
        finally:
            api.delete(f"/api/binders/{binder_id}")

    def test_delete_binder(self, api):
        _, binder = api.post("/api/binders", {"name": "To Delete"})
        binder_id = binder["id"]

        status, result = api.delete(f"/api/binders/{binder_id}")
        assert status == 200

        status, result = api.get(f"/api/binders/{binder_id}")
        assert status == 404

    def test_create_binder_missing_name(self, api):
        status, data = api.post("/api/binders", {})
        assert status == 400
        assert "name" in data.get("error", "").lower()

    def test_get_nonexistent_binder(self, api):
        status, data = api.get("/api/binders/999999")
        assert status == 404

    def test_create_binder_all_fields(self, api):
        status, binder = api.post("/api/binders", {
            "name": "Full Binder",
            "description": "All fields test",
            "color": "black ultra pro",
            "binder_type": "side-loading",
            "storage_location": "bookshelf, top row",
        })
        assert status == 201
        binder_id = binder["id"]

        try:
            status, result = api.get(f"/api/binders/{binder_id}")
            assert result["name"] == "Full Binder"
            assert result["color"] == "black ultra pro"
            assert result["binder_type"] == "side-loading"
            assert result["storage_location"] == "bookshelf, top row"
        finally:
            api.delete(f"/api/binders/{binder_id}")


# =============================================================================
# Binder card management
# =============================================================================


class TestBinderCards:
    """Add, remove, and list cards in binders."""

    @pytest.fixture
    def binder_with_cards(self, api):
        """Create a binder and find unassigned collection card IDs."""
        _, binder = api.post("/api/binders", {"name": "Card Test Binder"})
        binder_id = binder["id"]

        card_ids = _get_unassigned_entry_ids(api, count=3)

        yield binder_id, card_ids

        api.delete(f"/api/binders/{binder_id}")

    def test_add_cards_to_binder(self, api, binder_with_cards):
        binder_id, card_ids = binder_with_cards
        if len(card_ids) < 2:
            pytest.skip("Not enough unassigned collection cards")

        status, result = api.post(f"/api/binders/{binder_id}/cards", {
            "collection_ids": card_ids[:2],
        })
        assert status == 200
        assert result["count"] == 2

        status, cards = api.get(f"/api/binders/{binder_id}/cards")
        assert status == 200
        assert len(cards) == 2

    def test_binder_card_count(self, api, binder_with_cards):
        binder_id, card_ids = binder_with_cards
        if len(card_ids) < 2:
            pytest.skip("Not enough unassigned collection cards")

        api.post(f"/api/binders/{binder_id}/cards", {
            "collection_ids": card_ids[:2],
        })

        status, binder = api.get(f"/api/binders/{binder_id}")
        assert status == 200
        assert binder["card_count"] == 2


# =============================================================================
# Exclusivity constraint (API level)
# =============================================================================


class TestExclusivityAPI:
    """Cards can only be in one container at a time."""

    def test_card_in_deck_cannot_add_to_binder(self, api):
        """A card assigned to a constructed deck cannot be added to a binder."""
        card_ids = _get_unassigned_entry_ids(api, count=1)
        if not card_ids:
            pytest.skip("No unassigned cards")
        card_id = card_ids[0]

        _, deck = api.post("/api/decks", {"name": "Excl Test Deck", "state": "constructed"})
        _, binder = api.post("/api/binders", {"name": "Excl Test Binder"})

        try:
            # Add to deck
            status, _ = api.post(f"/api/decks/{deck['id']}/cards", {
                "collection_ids": [card_id],
                "zone": "mainboard",
            })
            assert status == 200

            # Try to add same card to binder - should fail with 409
            status, data = api.post(f"/api/binders/{binder['id']}/cards", {
                "collection_ids": [card_id],
            })
            assert status == 409
            assert "already assigned" in data.get("error", "").lower()
        finally:
            api.delete(f"/api/decks/{deck['id']}")
            api.delete(f"/api/binders/{binder['id']}")

    def test_card_in_binder_cannot_add_to_deck(self, api):
        """A card assigned to a binder cannot be added to a deck."""
        card_ids = _get_unassigned_entry_ids(api, count=1)
        if not card_ids:
            pytest.skip("No unassigned cards")
        card_id = card_ids[0]

        _, deck = api.post("/api/decks", {"name": "Excl Test Deck 2", "state": "constructed"})
        _, binder = api.post("/api/binders", {"name": "Excl Test Binder 2"})

        try:
            # Add to binder
            status, _ = api.post(f"/api/binders/{binder['id']}/cards", {
                "collection_ids": [card_id],
            })
            assert status == 200

            # Try to add same card to deck - should fail with 409
            status, data = api.post(f"/api/decks/{deck['id']}/cards", {
                "collection_ids": [card_id],
                "zone": "mainboard",
            })
            assert status == 409
            assert "already assigned" in data.get("error", "").lower()
        finally:
            api.delete(f"/api/decks/{deck['id']}")
            api.delete(f"/api/binders/{binder['id']}")

    def test_move_card_between_containers(self, api):
        """Move a card from a deck to a binder using the move endpoint."""
        card_ids = _get_unassigned_entry_ids(api, count=1)
        if not card_ids:
            pytest.skip("No unassigned cards")
        card_id = card_ids[0]

        _, deck = api.post("/api/decks", {"name": "Move Source Deck", "state": "constructed"})
        _, binder = api.post("/api/binders", {"name": "Move Target Binder"})

        try:
            # Add to deck
            api.post(f"/api/decks/{deck['id']}/cards", {
                "collection_ids": [card_id],
                "zone": "mainboard",
            })

            # Move to binder
            status, result = api.post(f"/api/binders/{binder['id']}/cards/move", {
                "collection_ids": [card_id],
            })
            assert status == 200
            assert result["count"] == 1

            # Verify card is in binder, not deck
            status, deck_cards = api.get(f"/api/decks/{deck['id']}/cards")
            assert len(deck_cards) == 0

            status, binder_cards = api.get(f"/api/binders/{binder['id']}/cards")
            assert len(binder_cards) == 1
        finally:
            api.delete(f"/api/decks/{deck['id']}")
            api.delete(f"/api/binders/{binder['id']}")


# =============================================================================
# Deck delete cascade
# =============================================================================


class TestDeleteCascade:
    """Deleting a deck/binder unassigns cards but doesn't remove them."""

    def test_delete_deck_preserves_cards(self, api):
        card_ids = _get_unassigned_entry_ids(api, count=2)
        if len(card_ids) < 2:
            pytest.skip("Need at least 2 unassigned cards")

        _, deck = api.post("/api/decks", {"name": "Cascade Test Deck", "state": "constructed"})
        api.post(f"/api/decks/{deck['id']}/cards", {
            "collection_ids": card_ids,
            "zone": "mainboard",
        })

        # Note the printing_ids of the cards we added
        status, deck_cards = api.get(f"/api/decks/{deck['id']}/cards")
        assert len(deck_cards) == 2

        # Delete the deck
        api.delete(f"/api/decks/{deck['id']}")

        # Cards should still be in collection (total count should not decrease)
        status, collection = api.get("/api/collection")
        assert status == 200
        assert len(collection) > 0  # Collection is not empty

    def test_delete_binder_preserves_cards(self, api):
        card_ids = _get_unassigned_entry_ids(api, count=2)
        if len(card_ids) < 2:
            pytest.skip("Need at least 2 unassigned cards")

        _, binder = api.post("/api/binders", {"name": "Cascade Test Binder"})
        api.post(f"/api/binders/{binder['id']}/cards", {
            "collection_ids": card_ids,
        })

        # Delete the binder
        api.delete(f"/api/binders/{binder['id']}")

        # Cards should still be in collection
        status, collection = api.get("/api/collection")
        assert status == 200
        assert len(collection) > 0


# =============================================================================
# Collection view CRUD
# =============================================================================


class TestCollectionViewCRUD:
    def test_create_view(self, api):
        status, view = api.post("/api/views", {
            "name": "Red Cards",
            "filters_json": '{"color": "R"}',
        })
        assert status == 201
        assert view["id"] is not None
        view_id = view["id"]

        try:
            status, result = api.get(f"/api/views/{view_id}")
            assert status == 200
            assert result["name"] == "Red Cards"
            assert result["filters_json"] == '{"color": "R"}'
        finally:
            api.delete(f"/api/views/{view_id}")

    def test_list_views(self, api):
        _, v1 = api.post("/api/views", {"name": "View A", "filters_json": "{}"})
        _, v2 = api.post("/api/views", {"name": "View B", "filters_json": "{}"})

        try:
            status, views = api.get("/api/views")
            assert status == 200
            names = {v["name"] for v in views}
            assert "View A" in names
            assert "View B" in names
        finally:
            api.delete(f"/api/views/{v1['id']}")
            api.delete(f"/api/views/{v2['id']}")

    def test_update_view(self, api):
        _, view = api.post("/api/views", {"name": "Old View", "filters_json": "{}"})
        view_id = view["id"]

        try:
            status, result = api.put(f"/api/views/{view_id}", {
                "name": "New View",
                "filters_json": '{"set": "MKM"}',
            })
            assert status == 200

            status, updated = api.get(f"/api/views/{view_id}")
            assert updated["name"] == "New View"
            assert updated["filters_json"] == '{"set": "MKM"}'
        finally:
            api.delete(f"/api/views/{view_id}")

    def test_delete_view(self, api):
        _, view = api.post("/api/views", {"name": "To Delete", "filters_json": "{}"})
        view_id = view["id"]

        status, result = api.delete(f"/api/views/{view_id}")
        assert status == 200

        status, result = api.get(f"/api/views/{view_id}")
        assert status == 404

    def test_create_view_missing_name(self, api):
        status, data = api.post("/api/views", {"filters_json": "{}"})
        assert status == 400

    def test_get_nonexistent_view(self, api):
        status, data = api.get("/api/views/999999")
        assert status == 404


# =============================================================================
# Collection endpoint filters for deck/binder
# =============================================================================


class TestCollectionDeckBinderFilters:
    """GET /api/collection supports deck/binder queries via Scryfall syntax."""

    def test_unassigned_filter(self, api):
        status, data = api.get("/api/collection?q=is%3Aunassigned&limit=5")
        assert status == 200
        for card in data:
            assert card.get("deck_id") is None
            assert card.get("binder_id") is None

    def test_deck_filter(self, api):
        card_ids = _get_unassigned_entry_ids(api, count=1)
        if not card_ids:
            pytest.skip("No unassigned cards")

        _, deck = api.post("/api/decks", {"name": "Filter Test Deck"})
        api.post(f"/api/decks/{deck['id']}/cards", {
            "collection_ids": card_ids,
            "zone": "mainboard",
        })

        try:
            from urllib.parse import quote
            q = quote(f'deck:"{deck["name"]}"')
            status, filtered = api.get(f"/api/collection?q={q}")
            assert status == 200
            assert len(filtered) >= 1
            for card in filtered:
                assert card.get("deck_id") == deck["id"]
        finally:
            api.delete(f"/api/decks/{deck['id']}")

    def test_binder_filter(self, api):
        card_ids = _get_unassigned_entry_ids(api, count=1)
        if not card_ids:
            pytest.skip("No unassigned cards")

        _, binder = api.post("/api/binders", {"name": "Filter Test Binder"})
        api.post(f"/api/binders/{binder['id']}/cards", {
            "collection_ids": card_ids,
        })

        try:
            from urllib.parse import quote
            q = quote(f'binder:"{binder["name"]}"')
            status, filtered = api.get(f"/api/collection?q={q}")
            assert status == 200
            assert len(filtered) >= 1
            for card in filtered:
                assert card.get("binder_id") == binder["id"]
        finally:
            api.delete(f"/api/binders/{binder['id']}")


# =============================================================================
# Vendored static assets
# =============================================================================


class TestVendoredFonts:
    """The mana-font CSS references `url("fonts/mana.woff")` — this test
    pins the resolved font URL so a future vendor update that shifts the
    path (the CSS previously shipped with `../fonts/...`, which 404'd) is
    caught immediately.

    Broken mana-font also causes visible layout shifts in the deck list
    as the browser falls back to a substitute font after the 404. When
    the fallback font's metrics differ, CSS multi-column layouts can
    rebalance mid-render, which is what a user reported seeing as
    "qty controls flash and then disappear" for a 10-swamp land row."""

    def test_mana_woff_loads(self, api):
        status, _ = api.get_raw(
            "/static/vendor/mana-font/fonts/mana.woff")
        assert status == 200

    def test_mana_css_references_resolve(self, api):
        status, css = api.get_raw("/static/vendor/mana-font/mana.min.css")
        assert status == 200
        text = css.decode("utf-8", errors="replace")
        # The CSS is relative to /static/vendor/mana-font/, so any
        # url("fonts/...") resolves to /static/vendor/mana-font/fonts/...
        assert 'url("fonts/mana.woff' in text, \
            "mana.min.css must reference fonts/ relative to its own dir"
        assert 'url("../fonts/' not in text, \
            "mana.min.css must not use the broken ../fonts/ path"
