"""
Hand-written implementation for deck_plan_progress_custom_query.

Sets a plan with a custom query target that matches cards in the deck,
verifies the progress count is nonzero.
"""


def steps(harness):
    # Set plan with a custom query that matches cards in deck 2.
    # Deck 2 has Phlage (burn/damage), Slick Sequence (damage),
    # and Bonny Pall — the oracle text query for destroy/exile/damage
    # should match at least Phlage and Slick Sequence.
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {"
        "removal: 5, "
        "'damage-dealers': {count: 6, "
        "query: \"card.oracle_text LIKE '%damage%'\", "
        "label: 'Damage Dealers'}"
        "}})})"
    )
    harness.page.wait_for_timeout(500)

    # Navigate to deck detail page
    harness.navigate("/decks/2")

    # Wait for plan section to render
    harness.wait_for_visible("#plan-section", timeout=10_000)

    # Verify the custom query label is shown
    harness.wait_for_text("Damage Dealers", timeout=5_000)
    harness.assert_text_present("Damage Dealers")

    # Verify the custom query target has nonzero progress.
    # Phlage and Slick Sequence both mention "damage" in oracle text.
    # The progress should show at least 2/6.
    harness.assert_text_present("2/6")

    # Verify the tag-based removal target shows separately
    harness.assert_text_present("removal")
    harness.assert_text_present("/5")

    harness.screenshot("final_state")
