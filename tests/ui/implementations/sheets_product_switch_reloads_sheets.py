"""
Hand-written implementation for sheets_product_switch_reloads_sheets.

Loads BLB via the deep link, switches to the collector product and back to
play, verifying each switch reloads the sheet content and rewrites the hash.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for the play render before touching a pill. The deep link loads
    # both products: loadProducts() auto-checks the first one (collector,
    # 6 sheets) and fires a sheet load for it, then setSelectedProduct()
    # switches to play and fires a second. Both paint .section-header, so only
    # the count tells them apart. 5 s (as in the sibling sheets scenarios)
    # because this is the page load, not an interaction.
    #
    # That double load is also why the deep link is the start page rather than
    # the set input: it means both products this scenario clicks have been
    # served once already, so each switch below measures the switch. Reaching
    # play through the pickers by hand put the set's *first* /api/sheets
    # inside the 500 ms interaction budget, and against a container that had
    # never served it the wait timed out every time (de-35k).
    harness.wait_for_text("8 sheets", timeout=5_000)

    # Switch to the collector product. The radio inputs are display:none, so
    # click the label.
    harness.click_by_text("collector", exact=True)

    # Sheets reload with collector's content: 6 sheets, and a sheet name play
    # does not have. ("Common" is no good as a discriminator — collector has
    # a foilCommon sheet, which renders as "Foil Common".)
    harness.wait_for_text("6 sheets")
    harness.assert_text_present("Showcase Rare Mythic")

    # The hash follows the selection, so the view stays shareable.
    url = harness.page.url
    assert "product=collector" in url, f"Expected product=collector in URL, got: {url}"

    harness.screenshot("collector_selected")

    # Switch back to play and confirm the content reloads the other way.
    harness.click_by_text("play", exact=True)
    harness.wait_for_text("8 sheets")
    harness.assert_text_present("Rare Mythic With Showcase")
    url = harness.page.url
    assert "product=play" in url, f"Expected product=play in URL, got: {url}"

    harness.screenshot("final_state")
