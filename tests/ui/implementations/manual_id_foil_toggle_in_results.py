"""
Hand-written implementation for manual_id_foil_toggle_in_results.

Resolves a card, toggles foil on and off, verifies visual state changes.
"""


def steps(harness):
    harness.navigate("/ingestor-ids")
    harness.wait_for_visible("#cn-input")

    # Add a valid entry
    harness.fill_by_selector("#cn-input", "100")
    harness.fill_by_selector("#set-input", "fdn")
    harness.click_by_selector("#add-btn")

    # Resolve
    harness.click_by_selector("#resolve-btn")
    harness.wait_for_text("Beast-Kin Ranger", timeout=10000)

    # Toggle foil on (click the inactive "--" toggle)
    harness.click_by_selector(".foil-toggle")
    harness.assert_visible(".foil-toggle.active")

    # Toggle foil off
    harness.click_by_selector(".foil-toggle")
    harness.assert_visible(".foil-toggle.inactive")

    harness.screenshot("final_state")
