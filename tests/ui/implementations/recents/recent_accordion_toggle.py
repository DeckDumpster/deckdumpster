"""
Hand-written implementation for recent_accordion_toggle.

The generated version clicked "Foil" text which matches a hidden <option>
in the binder assignment dropdown. The intent is about toggling the
accordion by clicking a card photo, not clicking a foil badge.

Flow: click card photo → accordion opens → click same photo → accordion closes.
"""


def steps(harness):
    # Click the second card (Arenson's Aura — has candidates, reliable label).
    harness.click_by_text("Arenson's Aura")
    # Verify the accordion panel opened.
    harness.assert_visible("#accordion-panel.open")
    # Click the same card again to collapse.
    harness.click_by_text("Arenson's Aura")
    # Verify the accordion is closed.
    harness.assert_hidden("#accordion-panel.open")
    harness.screenshot("final_state")
