"""
Hand-written implementation for deck_plan_custom_query_display.

Sets a plan with mixed int and custom query targets, verifies
the sidebar shows the custom label text.
"""


def steps(harness):
    # Set plan with mixed targets on deck 2
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {"
        "lands: 37, ramp: 8, removal: 5, "
        "'big-eldrazi': {count: 10, "
        "query: \"CAST(card.cmc AS INTEGER) >= 7 AND card.type_line LIKE '%Creature%'\", "
        "label: 'Big Creatures (7+ MV)'}"
        "}})})"
    )
    harness.page.wait_for_timeout(500)

    # Navigate to deck detail page
    harness.navigate("/decks/2")

    # Wait for plan section to render
    harness.wait_for_visible("#plan-section", timeout=10_000)

    # Verify custom query label is displayed (not the raw key "big eldrazi")
    harness.wait_for_text("Big Creatures (7+ MV)", timeout=5_000)
    harness.assert_text_present("Big Creatures (7+ MV)")

    # Verify tag-based targets show their tag names
    harness.assert_text_present("ramp")
    harness.assert_text_present("removal")

    # Verify counts are displayed
    harness.assert_text_present("0/10")
    harness.assert_text_present("/8")
    harness.assert_text_present("/5")

    harness.screenshot("final_state")
