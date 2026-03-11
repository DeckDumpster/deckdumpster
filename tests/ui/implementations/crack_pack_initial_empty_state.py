"""
Hand-written implementation for crack_pack_initial_empty_state.

Loads the Crack-a-Pack page and verifies all disabled-state defaults:
set input placeholder, disabled buttons, pack header text, picks panel.
"""


def steps(harness):
    # Harness auto-navigates to /crack (from hint start_page)
    harness.wait_for_visible("#set-input")

    # Wait for sets to finish loading (placeholder changes from "Loading sets...")
    harness.wait_for_visible('#set-input[placeholder="Search sets..."]')

    # Verify all action buttons are disabled
    harness.assert_visible("#open-btn[disabled]")
    harness.assert_visible("#reveal-all-btn[disabled]")
    harness.assert_visible("#sheets-btn[disabled]")

    # Verify pack header shows initial message
    harness.assert_text_present("Select a set and open a pack")

    # Verify picks panel shows empty state
    harness.assert_text_present("(0)")
    harness.assert_text_present("Click cards to pick them")

    harness.screenshot("final_state")
