"""
Hand-written implementation for card_detail_delete_copy.

Deletes an owned copy. The test runner auto-accepts the confirm() dialog.
"""


def steps(harness):
    # start_page: /card/lci/113 — auto-navigated by test runner.
    harness.wait_for_text("Preacher of the Schism")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=10_000)
    harness.screenshot("before_delete")
    # Click the Delete button. The confirm() dialog is auto-accepted by
    # the test runner's dialog handler.
    harness.click_by_selector(".delete-copy-btn")
    # The copy section should disappear after deletion.
    harness.wait_for_hidden(".copy-section", timeout=10_000)
    harness.screenshot("final_state")
