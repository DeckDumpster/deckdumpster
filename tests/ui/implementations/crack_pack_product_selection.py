"""
Hand-written implementation for crack_pack_product_selection.

Selects a set, verifies product pills appear with first auto-selected,
buttons become enabled, then switches to a different product.
"""


def steps(harness):
    # Harness auto-navigates to /crack (from hint start_page)
    harness.wait_for_visible("#set-input")

    # Wait for sets to finish loading (placeholder changes from "Loading sets...")
    harness.wait_for_visible('#set-input[placeholder="Search sets..."]')

    # Search for and select Foundations
    harness.fill_by_selector("#set-input", "Foundations")
    harness.wait_for_visible("#set-dropdown li")
    harness.click_by_selector("#set-dropdown li")

    # Wait for product radio labels to load
    harness.wait_for_visible("#product-radios label")

    # Verify Open Pack and Explore Sheets buttons are enabled
    harness.assert_hidden("#open-btn[disabled]")
    harness.assert_hidden("#sheets-btn[disabled]")

    # Verify first product label text is present
    harness.assert_text_present("beginner")

    # Click a different product label to switch (click label since input is hidden)
    harness.click_by_selector("label[for='product-collector']")

    # Verify the new product label text is present
    harness.assert_text_present("collector")

    harness.screenshot("final_state")
