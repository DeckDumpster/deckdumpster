"""
Hand-written implementation for homepage_nav_links_collection.
Clicks each Collection group link and verifies navigation to the correct page.
Batches is excluded (covered by batches_homepage_nav_link).
"""


def steps(harness):
    # start_page: / — auto-navigated by test runner.

    # Click Cards link and verify navigation.
    # The h1 on /collection says "Collection" (title is "Collection Browser").
    harness.click_by_selector("a[href='/collection']")
    harness.wait_for_text("Collection")
    harness.navigate("/")

    # Click Decks link and verify navigation
    harness.click_by_selector("a[href='/decks']")
    harness.wait_for_text("Decks")
    harness.navigate("/")

    # Click Binders link and verify navigation
    harness.click_by_selector("a[href='/binders']")
    harness.wait_for_text("Binders")
    harness.navigate("/")

    # Click Sealed link and verify navigation
    harness.click_by_selector("a[href='/sealed']")
    harness.wait_for_text("Sealed Collection")

    harness.screenshot("final_state")
