"""
Hand-written implementation for card_detail_dfc_flip.

Navigates to a DFC card (Ojer Axonil), verifies front face, flips to back,
and verifies back face name and type appear.
"""


def steps(harness):
    # start_page: /card/lci/158 — auto-navigated by test runner.
    # Verify front face loads.
    harness.wait_for_text("Ojer Axonil, Deepest Might")
    harness.assert_text_present("Ojer Axonil, Deepest Might")
    harness.assert_text_present("Legendary Creature")
    harness.screenshot("front_face")
    # Click the flip button.
    harness.click_by_selector("#flip-btn")
    # Back face should show.
    harness.wait_for_text("Temple of Power")
    harness.assert_text_present("Temple of Power")
    harness.assert_text_present("Land")
    harness.screenshot("final_state")
