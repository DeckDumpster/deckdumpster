"""
Hand-written implementation for deck_replace_modal_open_and_suggestions.

Opens the replace modal from a grid card and verifies role-based suggestions appear.
"""


def steps(harness):
    # Set plan on deck 2 so cards have plan-relevant tags
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {removal: 3, ramp: 2, draw: 2}})})"
    )
    harness.page.wait_for_timeout(500)

    # Navigate to deck detail page
    harness.navigate("/decks/2")
    harness.wait_for_visible("#card-grid", timeout=10_000)

    # Switch to grid view
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_visible("#card-grid .sheet-card", timeout=5_000)
    harness.screenshot("grid_view")

    # Click replace button on a card (Slick Sequence, data-cid=22)
    harness.click_by_selector('.replace-btn[data-cid="22"]')

    # Wait for replace modal to open
    harness.wait_for_visible("#replace-modal.active", timeout=5_000)

    # Verify card name in header
    harness.assert_text_present("Slick Sequence")

    # Wait for suggestions to load (role column should have at least one candidate)
    harness.wait_for_visible("#replace-role .replace-candidate", timeout=5_000)
    harness.assert_text_present("Cathar Commando")

    # Verify candidate has thumbnail and name
    harness.assert_visible("#replace-role .replace-thumb")
    harness.assert_visible("#replace-role .replace-candidate-name")

    harness.screenshot("final_state")
