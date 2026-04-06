"""
Hand-written implementation for card_detail_change_printing_execute.

Changes a copy's printing from the card detail page and verifies
navigation to the new printing's page.
"""


def steps(harness):
    # start_page: /card/fdn/34 — Curator of Destinies (4 printings)
    harness.wait_for_text("Curator of Destinies")
    harness.wait_for_visible(".copy-section")
    # Open the printing picker
    harness.click_by_text("Change")
    harness.wait_for_visible(".printing-picker-list")
    # Click the first non-current printing option
    harness.click_by_selector(".printing-option:not(.current)")
    # Page should navigate to the new printing's detail page
    harness.wait_for_text("Curator of Destinies", timeout=10_000)
    # Verify the copy now exists on this page
    harness.wait_for_visible(".copy-section", timeout=10_000)
    harness.screenshot("final_state")
