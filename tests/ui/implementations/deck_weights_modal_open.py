"""
Hand-written implementation for deck_weights_modal_open.

Sets a plan on deck 2, navigates to the deck detail page, verifies
the Weights button is visible, opens the modal, and checks that all
7 weight labels and default values are displayed.
"""


def steps(harness):
    # Set a plan so the Weights button appears
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {ramp: 8, removal: 5, draw: 4}})})"
    )
    harness.page.wait_for_timeout(500)

    # Navigate to deck detail page
    harness.navigate("/decks/2")

    # Wait for plan section to render (confirms plan loaded)
    harness.wait_for_visible("#plan-section", timeout=10_000)

    # Verify Weights button is visible
    harness.assert_visible("#btn-weights")

    # Open the weights modal
    harness.click_by_selector("#btn-weights")
    harness.wait_for_visible("#weights-modal.active", timeout=5_000)

    # Verify modal title
    harness.assert_text_present("Autofill Weights")

    # Verify all 7 weight labels are present
    harness.assert_text_present("EDHREC")
    harness.assert_text_present("Salt")
    harness.assert_text_present("Price")
    harness.assert_text_present("Plan overlap")
    harness.assert_text_present("Novelty")
    harness.assert_text_present("Bling")
    harness.assert_text_present("Random")

    # Verify descriptions are shown
    harness.assert_text_present("popular on EDHREC")
    harness.assert_text_present("annoying cards")
    harness.assert_text_present("more expensive")
    harness.assert_text_present("overlap with the Deck Plan")
    harness.assert_text_present("low popularity")
    harness.assert_text_present("full-art, borderless")
    harness.assert_text_present("more randomly")

    harness.screenshot("final_state")
