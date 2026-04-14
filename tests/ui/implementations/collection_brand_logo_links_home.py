"""
Hand-written implementation for collection_brand_logo_links_home.

Verifies the new card-stack brand logo in the collection header links
back to the homepage. Replaces the role of the removed "Collection"
title row as the way to navigate out of the collection view.
"""


def steps(harness):
    # start_page: /collection — auto-navigated by test runner.
    harness.wait_for_visible("#search-input")

    # Brand logo sits immediately left of the search box.
    harness.assert_visible("a.brand-logo")
    harness.assert_visible("a.brand-logo[href='/']")

    # Clicking the logo navigates to the homepage.
    harness.click_by_selector("a.brand-logo")
    harness.wait_for_text("MTG Collection Tools")

    harness.screenshot("final_state")
