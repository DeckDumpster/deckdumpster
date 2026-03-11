"""
Hand-written implementation for recent_navigation_header.

Verifies header navigation links on the Recent Images page.
"""


def steps(harness):
    # Navigate to Recent Images page
    harness.navigate("/recent")
    harness.wait_for_visible("header")

    # Verify header title
    harness.assert_text_present("Recent Images")

    # Verify navigation links exist
    harness.assert_visible("header a[href='/']")
    harness.assert_visible("header a[href='/upload']")
    harness.assert_visible("header a[href='/disambiguate']")

    # Click Upload link to verify navigation
    harness.click_by_selector("header a[href='/upload']")
    harness.wait_for_visible("#drop-zone")

    harness.screenshot("final_state")
