"""
Hand-written implementation for user_switching_different_collections.

Comprehensive multi-user isolation test:
1. Create two users, verify default has demo data and new user is empty
2. Switch to new user, add cards via API, verify they appear
3. Switch back to default, verify original data unchanged
4. Delete a card from default, verify it's gone
5. Switch to new user again, verify their collection is untouched
"""

import json
import ssl
import urllib.request


def _api(base_url, method, path, data=None, cookie=None):
    """Make an API call to the test instance."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{base_url}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", f"mtgc_user={cookie}")
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read())


def _collection_count(base, user):
    """Get the number of owned collection entries for a user."""
    items = _api(base, "GET", "/api/collection?status=owned", cookie=user)
    return len(items)


def _set_user(harness, user):
    """Switch the browser to a different user."""
    harness.page.context.add_cookies([{
        "name": "mtgc_user",
        "value": user,
        "url": harness.base_url,
    }])


def steps(harness):
    base = harness.base_url

    # ── Setup: create users to activate multi-user mode ──
    _api(base, "POST", "/api/users", {"name": "alice"})
    _api(base, "POST", "/api/users", {"name": "bob"})

    # ── 1. Verify default user has demo data ──
    default_count = _collection_count(base, "default")
    assert default_count > 0, f"Default user should have demo cards, got {default_count}"

    _set_user(harness, "default")
    harness.navigate("/collection")
    harness.wait_for_text("entries")
    harness.assert_text_present("entries")
    # Capture the exact status text for later comparison
    default_status = harness.page.locator("#status").text_content()
    harness.screenshot("01_default_collection")

    # ── 2. Verify new users start empty ──
    assert _collection_count(base, "alice") == 0
    assert _collection_count(base, "bob") == 0

    # ── 3. Switch to alice, add cards via API ──
    # Look up a printing_id from shared reference data (FDN #132)
    card_info = _api(base, "GET", "/api/card/by-set-cn?set=fdn&cn=132", cookie="alice")
    printing_id = card_info["printing_id"]

    # Add 2 cards to alice's collection
    _api(base, "POST", "/api/collection", {
        "printing_id": printing_id, "finish": "nonfoil",
    }, cookie="alice")
    _api(base, "POST", "/api/collection", {
        "printing_id": printing_id, "finish": "foil",
    }, cookie="alice")

    assert _collection_count(base, "alice") == 2

    # Verify alice sees her cards in the UI
    _set_user(harness, "alice")
    harness.navigate("/collection")
    harness.wait_for_text("entries")
    harness.assert_text_present("2 entries")
    harness.screenshot("02_alice_with_cards")

    # ── 4. Switch back to default — should be unchanged ──
    _set_user(harness, "default")
    harness.navigate("/collection")
    harness.wait_for_text("entries")
    restored_status = harness.page.locator("#status").text_content()
    assert restored_status == default_status, (
        f"Default collection changed! Before: {default_status}, After: {restored_status}"
    )
    harness.screenshot("03_default_unchanged")

    # ── 5. Delete a card from default ──
    default_items = _api(base, "GET", "/api/collection?status=owned&expand=copies", cookie="default")
    delete_id = default_items[0]["collection_id"]
    _api(base, "POST", "/api/collection/bulk-delete", {"ids": [delete_id]}, cookie="default")

    new_default_count = _collection_count(base, "default")
    assert new_default_count == default_count - 1, (
        f"Expected {default_count - 1} after delete, got {new_default_count}"
    )

    # Verify the delete shows in the UI
    harness.navigate("/collection")
    harness.wait_for_text("entries")
    harness.screenshot("04_default_after_delete")

    # ── 6. Switch to alice — her 2 cards should be untouched ──
    assert _collection_count(base, "alice") == 2
    _set_user(harness, "alice")
    harness.navigate("/collection")
    harness.wait_for_text("entries")
    harness.assert_text_present("2 entries")
    harness.screenshot("05_alice_still_has_cards")

    # ── 7. Bob should still be empty ──
    assert _collection_count(base, "bob") == 0

    # ── 8. Create a deck for alice, verify it doesn't leak to bob ──
    _api(base, "POST", "/api/decks", {"name": "Alice Deck"}, cookie="alice")
    alice_decks = _api(base, "GET", "/api/decks", cookie="alice")
    assert len(alice_decks) == 1
    assert alice_decks[0]["name"] == "Alice Deck"

    bob_decks = _api(base, "GET", "/api/decks", cookie="bob")
    assert len(bob_decks) == 0, f"Bob shouldn't see Alice's deck, got {bob_decks}"

    harness.screenshot("final_state")
