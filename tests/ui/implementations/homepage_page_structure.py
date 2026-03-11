"""
Hand-written implementation for homepage_page_structure.
Verifies the homepage displays all three navigation groups with expected
links, subtitle descriptions, and the Settings section.
"""


def steps(harness):
    # Navigate to homepage
    harness.navigate("/")

    # Verify page header
    harness.assert_text_present("MTG Collection Tools")

    # Verify Collection group label and links
    harness.assert_text_present("Collection")
    harness.assert_text_present("Cards")
    harness.assert_text_present("Decks")
    harness.assert_text_present("Binders")
    harness.assert_text_present("Sealed")
    harness.assert_text_present("Batches")

    # Verify Analysis group label and links
    harness.assert_text_present("Analysis")
    harness.assert_text_present("Crack-a-Pack")
    harness.assert_text_present("Explore Sheets")
    harness.assert_text_present("Set Value")

    # Verify Add Cards group label and links
    harness.assert_text_present("Add Cards")
    harness.assert_text_present("Upload")
    harness.assert_text_present("Recent")
    harness.assert_text_present("Corners")
    harness.assert_text_present("Manual ID")
    harness.assert_text_present("Orders")
    harness.assert_text_present("CSV Import")

    # Verify subtitle descriptions are present
    harness.assert_text_present("Browse with search, filters, and prices")
    harness.assert_text_present("Organize into decks with zones")

    # Verify Settings section
    harness.assert_text_present("Settings")
    harness.assert_text_present("Image Display")
    harness.assert_text_present("Price Sources")
    harness.assert_text_present("Crop")
    harness.assert_text_present("Contain")
    harness.assert_text_present("TCG")
    harness.assert_text_present("CK")

    harness.screenshot("final_state")
