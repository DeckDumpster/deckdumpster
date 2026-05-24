"""
Hand-written implementation for card_modal_dispose_button_disabled_until_status_selected.

Opens a card modal via grid view, asserts the Dispose button is
disabled by default, picks a disposition, and asserts the button
becomes enabled.
"""


def steps(harness):
    harness.navigate("/collection")
    # Grid view is the stable click path — clicking table rows can hit
    # header-filter cells in Playwright (see project memory).
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_visible(".sheet-card[data-idx='0']")

    # Open the card modal.
    harness.click_by_selector(".sheet-card[data-idx='0']")
    # The copies section is fetched lazily; wait for the dispose UI to
    # land.
    harness.wait_for_visible(".dispose-btn", timeout=5_000)

    # Default state: button is rendered with the disabled attribute.
    harness.assert_visible(".dispose-btn[disabled]")

    # Pick a disposition — the change handler enables the button.
    harness.select_by_label(".dispose-select", "Sold")
    harness.assert_visible(".dispose-btn:not([disabled])")
    harness.screenshot("final_state")
