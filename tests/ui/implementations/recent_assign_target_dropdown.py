"""
Hand-written implementation for recent_assign_target_dropdown.

Verifies the assign target dropdown is populated with decks and binders.
"""


def steps(harness):
    # Wait for grid and image cards to load (async via loadRecent).
    # By the time images render, loadAssignTargets() has also completed
    # because navigate() waits for networkidle.
    harness.wait_for_visible("#grid")
    harness.wait_for_visible(".img-card")
    harness.assert_visible("#assign-target")

    # Verify deck option elements exist in the DOM.  <option> elements
    # inside a closed <select> are "hidden" to Playwright, so use
    # assert_element_count on a CSS selector instead of wait_for_text.
    harness.assert_element_count("#assign-target option[value^='deck:']", 2)
    harness.assert_element_count("#assign-target option[value^='binder:']", 2)

    # Verify default option text (visible as the select's displayed value)
    harness.assert_text_present("No assignment")

    # Verify deck entries exist in the DOM
    harness.assert_text_present("Bolt Tribal")
    harness.assert_text_present("Eldrazi Ramp")

    # Verify binder entries exist in the DOM
    harness.assert_text_present("Trade Binder")
    harness.assert_text_present("Foil Collection")

    harness.screenshot("final_state")
