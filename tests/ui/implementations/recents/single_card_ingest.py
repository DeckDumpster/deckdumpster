"""
Single-card ingest from the accordion sidebar.

Opens the recent page, clicks a confirmed card to open the accordion,
verifies the "Add to Collection" button is visible, clicks it, and
confirms the card is removed from the grid while others remain.

Requires demo ingest images (4 images from --test fixture: 2 DONE, 2 ERROR).
"""


def steps(harness):
    # Wait for demo ingest cards to appear in the grid.
    harness.wait_for_visible(".img-card", timeout=500)

    # All 4 demo images should be present (2 DONE, 2 ERROR).
    harness.assert_element_count(".img-card", 4)

    # Click the first card to open the accordion sidebar.
    harness.click_by_selector(".img-card")
    harness.wait_for_visible(".acc-sidebar", timeout=500)

    # The "Add to Collection" button should be visible for a confirmed card.
    harness.assert_text_present("Add to Collection")

    harness.screenshot("accordion_with_ingest_button")

    # Click "Add to Collection" to ingest just this one card.
    harness.click_by_text("Add to Collection", exact=True)

    # After ingest, the card should be removed from the grid.
    # Wait for grid to shrink to 3 cards.
    harness.wait_for_hidden(".accordion-panel.open", timeout=500)
    harness.assert_element_count(".img-card", 3)

    harness.screenshot("after_single_ingest")
