"""
Hand-written implementation for collection_search_autocomplete_keywords.

Types "c:" to trigger autocomplete, verifies color suggestions appear,
then selects one to insert it.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible("#search-input")

    # Type "c:" to trigger value autocomplete for colors
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "c:")

    # Autocomplete dropdown should appear with color value suggestions
    harness.wait_for_visible("#ac-dropdown")
    # Values are short codes: w, u, b, r, g
    harness.assert_text_present("azorius")
    harness.screenshot("autocomplete_colors")

    # Click a suggestion to insert it
    harness.click_by_text("r")

    # Dropdown should close after selection
    harness.wait_for_hidden("#ac-dropdown")
    harness.screenshot("final_state")
