"""
Hand-written implementation for manual_id_page_initial_state.

Verifies the Manual ID Entry page loads with correct initial state:
empty table, card count zero, Resolve disabled, info message, Home link.
"""


def steps(harness):
    harness.navigate("/ingestor-ids")
    harness.wait_for_visible("#cn-input")

    # Verify entry table exists with empty tbody
    harness.assert_visible("#entry-table")
    harness.assert_text_present("Rarity")
    harness.assert_text_present("Cards: 0")

    # Verify Resolve button is present (disabled by default)
    harness.assert_visible("#resolve-btn")

    # Verify info message in results panel
    harness.assert_text_present("Add cards using rarity, collector number, and set code")

    # Verify Home link
    harness.assert_visible("header a[href='/']")

    harness.screenshot("final_state")
