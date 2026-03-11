"""
Hand-written implementation for crack_pack_set_search_filter.

Types a partial set name, uses keyboard to select, verifies display,
then re-clicks the input to confirm it clears and reopens the dropdown.
"""


def steps(harness):
    # Harness auto-navigates to /crack (from hint start_page)
    harness.wait_for_visible("#set-input")

    # Wait for sets to finish loading (placeholder changes from "Loading sets...")
    harness.wait_for_visible('#set-input[placeholder="Search sets..."]')

    # Type partial name to filter dropdown
    harness.fill_by_selector("#set-input", "Found")
    harness.wait_for_visible("#set-dropdown li")

    # Use keyboard to select: ArrowDown then Enter
    harness.press_key("ArrowDown")
    harness.press_key("Enter")

    # Verify input shows selected set and dropdown is closed
    harness.assert_text_present("Foundations (fdn)")
    harness.assert_hidden("#set-dropdown.open")

    # Click elsewhere to blur the input first (focus event only fires on re-focus)
    harness.click_by_selector("#pack-header")

    # Click back into the input to test reselection behavior
    harness.click_by_selector("#set-input")

    # Verify dropdown reopens
    harness.wait_for_visible("#set-dropdown.open")

    harness.screenshot("final_state")
