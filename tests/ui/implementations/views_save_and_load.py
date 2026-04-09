"""
Hand-written implementation for views_save_and_load.

The demo fixture has a saved view "Modern Staples" with filter q=crawler.
Loading it should filter the collection to show Scrawling Crawler cards.
"""


def steps(harness):
    # Open the more menu.
    harness.click_by_selector("#more-menu-btn")
    # Select the "Modern Staples" saved view from the dropdown.
    harness.select_by_label("#view-select", "Modern Staples")
    # Verify that the search filtered to show Scrawling Crawler.
    harness.wait_for_text("Scrawling Crawler")
    harness.screenshot("final_state")
