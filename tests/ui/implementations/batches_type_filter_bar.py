"""
Hand-written implementation for batches_type_filter_bar.

Verifies the type filter pill bar on the Batches page filters the batch list.
"""


def steps(harness):
    # Navigate to the Batches page
    harness.navigate("/batches")
    # Wait for the batch list to load
    harness.wait_for_text("Wednesday evening scan")

    # The 5 expected filter pills are present in the filter bar.
    # Assert directly against the filter-bar scope so a stray "Orders"
    # link elsewhere on the page can't make this test silently pass.
    harness.assert_element_count("#type-filter .pill", 5)
    harness.assert_visible("#type-filter .pill[data-type='']")
    harness.assert_visible("#type-filter .pill[data-type='corner']")
    harness.assert_visible("#type-filter .pill[data-type='ocr']")
    harness.assert_visible("#type-filter .pill[data-type='csv_import']")
    harness.assert_visible("#type-filter .pill[data-type='manual_id']")
    # Orders are a peer resource at /orders — no filter pill for them.
    harness.assert_element_count("#type-filter .pill[data-type='order']", 0)

    # Click the "Corner" filter pill
    harness.click_by_text("Corner")
    # Verify corner batches are still visible (demo data is all corner type)
    harness.wait_for_text("Wednesday evening scan")
    harness.assert_text_present("New cards from LGS")
    # Click "All" to reset the filter
    harness.click_by_text("All")
    harness.wait_for_text("Wednesday evening scan")
    harness.screenshot("final_state")
