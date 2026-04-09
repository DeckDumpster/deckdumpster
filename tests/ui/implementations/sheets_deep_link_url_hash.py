"""
Hand-written implementation for sheets_deep_link_url_hash.

Navigates directly to /sheets#set=blb&product=play and verifies
the page auto-populates set, product, and sheet content.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for sheet sections to render (proves data loaded)
    harness.wait_for_visible(".section-header", timeout=500)

    # Verify the set input auto-filled with Bloomburrow (input value, not text)
    val = harness.page.input_value("#set-input")
    assert "Bloomburrow" in val or "blb" in val.lower(), f"Expected Bloomburrow in input, got: {val}"

    # Verify the play product is shown and sheets loaded
    harness.assert_text_present("play")

    # Verify status text shows the expected sheet count
    harness.assert_text_present("8 sheets")

    # Verify Common sheet exists (unique to play product)
    harness.assert_text_present("Common")

    harness.screenshot("final_state")
