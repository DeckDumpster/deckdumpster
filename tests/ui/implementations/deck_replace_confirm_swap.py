"""
Hand-written implementation for deck_replace_confirm_swap.

Selects a replacement candidate and confirms the swap.
"""


def steps(harness):
    # Set plan on deck 2
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {removal: 3, ramp: 2, draw: 2}})})"
    )
    harness.page.wait_for_timeout(500)

    # Clear localStorage to ensure fresh table view, then navigate
    harness.page.evaluate("localStorage.removeItem('deckGridCols')")
    harness.navigate("/decks/2")

    # Ensure table view (default) and verify Slick Sequence is present
    harness.click_by_selector("#view-table-btn")
    harness.wait_for_visible("#card-table", timeout=10_000)
    harness.assert_text_present("Slick Sequence")

    # Switch to grid view for replace button access
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_visible("#card-grid .sheet-card", timeout=5_000)

    # Open replace modal
    harness.click_by_selector('.replace-btn[data-cid="22"]')
    harness.wait_for_visible("#replace-modal.active", timeout=5_000)

    # Wait for role suggestions to load
    harness.wait_for_visible("#replace-role .replace-candidate", timeout=5_000)

    # Click the first candidate
    harness.click_by_selector("#replace-role .replace-candidate")

    # Verify selection state
    harness.assert_visible("#replace-role .replace-candidate.selected")
    harness.screenshot("candidate_selected")

    # Click Confirm
    harness.click_by_selector("#replace-confirm")

    # Modal should close
    harness.wait_for_hidden("#replace-modal.active", timeout=5_000)

    # Wait for deck to reload, then re-navigate to get fresh state
    harness.page.wait_for_timeout(1500)
    harness.navigate("/decks/2")
    harness.click_by_selector("#view-table-btn")
    harness.wait_for_visible("#card-table", timeout=10_000)
    harness.page.wait_for_timeout(500)

    # Slick Sequence should be gone, replacement should be present
    harness.assert_text_absent("Slick Sequence")
    harness.assert_text_present("Cathar Commando")

    harness.screenshot("final_state")
