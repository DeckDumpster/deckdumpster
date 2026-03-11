"""
Hand-written implementation for homepage_nav_links_analysis_and_addcards.
Clicks each Analysis and Add Cards group link, verifying navigation.
Also verifies the OCR subgroup label is visible.
"""


def steps(harness):
    # Navigate to homepage
    harness.navigate("/")

    # Verify OCR subgroup label is visible
    harness.assert_visible(".nav-subgroup .sub-label")
    harness.assert_text_present("OCR")

    # --- Analysis group ---

    # Click Crack-a-Pack and verify
    harness.click_by_selector("a[href='/crack']")
    harness.wait_for_text("Crack-a-Pack")
    harness.navigate("/")

    # Click Explore Sheets and verify
    harness.click_by_selector("a[href='/sheets']")
    harness.wait_for_text("Explore Sheets")
    harness.navigate("/")

    # Click Set Value and verify
    harness.click_by_selector("a[href='/set-value']")
    harness.wait_for_text("Set Value")
    harness.navigate("/")

    # --- Add Cards group ---

    # Click Upload and verify
    harness.click_by_selector("a[href='/upload']")
    harness.wait_for_text("Upload")
    harness.navigate("/")

    # Click Recent and verify
    harness.click_by_selector("a[href='/recent']")
    harness.wait_for_text("Recent")
    harness.navigate("/")

    # Click Corners and verify
    harness.click_by_selector("a[href='/ingest-corners']")
    harness.wait_for_text("Corners")
    harness.navigate("/")

    # Click Manual ID and verify
    harness.click_by_selector("a[href='/ingestor-ids']")
    harness.wait_for_text("Manual ID")
    harness.navigate("/")

    # Click Orders and verify
    harness.click_by_selector("a[href='/ingestor-order']")
    harness.wait_for_text("Order")
    harness.navigate("/")

    # Click CSV Import and verify
    harness.click_by_selector("a[href='/import-csv']")
    harness.wait_for_text("CSV Import")

    harness.screenshot("final_state")
