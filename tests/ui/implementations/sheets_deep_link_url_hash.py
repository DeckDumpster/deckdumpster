"""
Hand-written implementation for sheets_deep_link_url_hash.

Navigates directly to /sheets#set=blb&product=play and verifies
the page auto-populates set, product, and sheet content.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for the status text to settle on the final sheet count.
    # explore_sheets.html updates #status only after the section-render
    # loop completes, so waiting on .section-header alone races the
    # status update on slower runners.
    harness.wait_for_text("8 sheets", timeout=5_000)

    # Verify the set input auto-filled with Bloomburrow (input value, not text)
    val = harness.page.input_value("#set-input")
    assert "Bloomburrow" in val or "blb" in val.lower(), f"Expected Bloomburrow in input, got: {val}"

    # Verify the play product is shown and sheets loaded
    harness.assert_text_present("play")

    # Verify Common sheet exists (unique to play product)
    harness.assert_text_present("Common")

    harness.screenshot("final_state")
