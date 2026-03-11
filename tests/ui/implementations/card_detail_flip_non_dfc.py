"""
Hand-written implementation for card_detail_flip_non_dfc.

Flips a non-DFC card to show the generic card back, verifies the details
panel is unchanged, then flips back to the front face.
"""


def steps(harness):
    # start_page: /card/fdn/191 — auto-navigated by test runner.
    harness.wait_for_text("Brazen Scourge")
    harness.wait_for_visible("#flip-btn", timeout=10_000)
    # Click the flip button.
    harness.click_by_selector("#flip-btn")
    # Verify the card is flipped.
    harness.wait_for_visible("#card-flip.flipped", timeout=5_000)
    # Details panel should still show the same card name.
    harness.assert_text_present("Brazen Scourge")
    # Click flip again to return to front.
    harness.click_by_selector("#flip-btn")
    # Verify the card is no longer flipped.
    harness.wait_for_hidden("#card-flip.flipped", timeout=5_000)
    harness.assert_text_present("Brazen Scourge")
    harness.screenshot("final_state")
