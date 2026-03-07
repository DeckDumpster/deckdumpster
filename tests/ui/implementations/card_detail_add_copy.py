"""
Hand-written implementation for card_detail_add_copy.

Clicks Add, fills in purchase details, confirms, and verifies
a new copy appears in the Copies section.
"""


def steps(harness):
    # start_page: /card/blb/124 — auto-navigated by test runner.
    harness.wait_for_text("Artist's Talent")
    # Click "Add" to expand the add form.
    harness.click_by_selector("#add-btn")
    harness.wait_for_visible(".add-collection-form")
    # Fill in purchase details.
    harness.fill_by_selector("#add-price", "3.50")
    harness.fill_by_selector("#add-source", "LGS")
    # Confirm the addition.
    harness.click_by_selector("#add-confirm-btn")
    # Form should disappear and a new copy should appear.
    harness.wait_for_hidden(".add-collection-form")
    harness.wait_for_visible(".copy-section", timeout=10_000)
    harness.screenshot("final_state")
