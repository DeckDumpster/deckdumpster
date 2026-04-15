"""
Hand-written implementation for collection_search_unowned.

Verifies that "is:unowned" routes the collection query through the
LEFT-JOIN template and surfaces cards from the local database that
aren't in the user's collection. The fixture contains 0 owned "lotus"
rows but 3 unowned printings in the card database.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Default search for "lotus" — no owned lotus cards in the fixture
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "lotus")
    harness.wait_for_text("0 entries")
    harness.screenshot("default_lotus_empty")

    # Prepend is:unowned — three printings from the card DB appear
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "is:unowned lotus")
    harness.wait_for_text("3 entries")

    # Each of the three printings is named
    harness.assert_text_present("Gilded Lotus")
    harness.assert_text_present("Lotus Bloom")
    harness.assert_text_present("Lotus Petal")

    # Rows are dimmed via the .unowned class
    harness.assert_visible("tr.unowned")

    harness.screenshot("final_state")
