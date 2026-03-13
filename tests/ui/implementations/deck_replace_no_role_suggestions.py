"""
Hand-written implementation for deck_replace_no_role_suggestions.

Opens replace modal for a card with no plan tags, verifies empty role column.
"""


def steps(harness):
    # Set plan on deck 2
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {removal: 3, ramp: 2, draw: 2}})})"
    )
    harness.page.wait_for_timeout(500)

    harness.navigate("/decks/2")
    harness.wait_for_visible("#card-grid", timeout=10_000)

    # Switch to grid view
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_visible("#card-grid .sheet-card", timeout=5_000)

    # Open replace modal for Disruptor Flute (cid=23, tags=hate — no plan tags)
    harness.click_by_selector('.replace-btn[data-cid="23"]')
    harness.wait_for_visible("#replace-modal.active", timeout=5_000)

    # Verify card name
    harness.assert_text_present("Disruptor Flute")

    # Role column should show empty state
    harness.wait_for_text("No candidates found", timeout=5_000)

    # Search column should still be functional with inputs visible
    harness.assert_visible("#rs-name")
    harness.assert_visible("#rs-cmc")

    harness.screenshot("final_state")
