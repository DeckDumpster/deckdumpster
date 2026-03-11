"""
Hand-written implementation for disambiguate_navigation_links.

Loads the Disambiguate page and verifies header nav links, title,
and the empty state structure including the upload link.
"""


def steps(harness):
    # Navigate to Disambiguate page
    harness.navigate("/disambiguate")

    # Wait for empty state to appear
    harness.wait_for_visible("#empty-state")

    # Verify header title
    harness.assert_text_present("Disambiguate")

    # Verify navigation links are present
    harness.assert_text_present("Home")
    harness.assert_text_present("Upload")
    harness.assert_text_present("Recent")

    # Verify nav link elements exist
    harness.assert_visible("header a[href='/']")
    harness.assert_visible("header a[href='/upload']")
    harness.assert_visible("header a[href='/recent']")

    # Verify empty state message
    harness.assert_text_present("No cards to disambiguate")

    # Verify upload link in empty state
    harness.assert_text_present("Upload some photos")

    harness.screenshot("final_state")
