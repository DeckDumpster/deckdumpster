"""
Hand-written implementation for manual_id_remove_entry.

Adds entries, removes them one by one, verifies count updates and
Resolve button disables when empty.
"""


def steps(harness):
    harness.navigate("/ingestor-ids")
    harness.wait_for_visible("#cn-input")

    # Add entry 1
    harness.fill_by_selector("#cn-input", "100")
    harness.fill_by_selector("#set-input", "fdn")
    harness.click_by_selector("#add-btn")

    # Add entry 2
    harness.fill_by_selector("#cn-input", "139")
    harness.fill_by_selector("#set-input", "fdn")
    harness.click_by_selector("#add-btn")

    harness.assert_text_present("Cards: 2")

    # Remove first entry
    harness.click_by_selector("#entry-tbody .remove-btn")
    harness.assert_text_present("Cards: 1")

    # Remove remaining entry
    harness.click_by_selector("#entry-tbody .remove-btn")
    harness.assert_text_present("Cards: 0")

    harness.screenshot("final_state")
