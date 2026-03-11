"""
Hand-written implementation for manual_id_keyboard_rapid_entry.

Tests the keyboard-driven rapid entry flow: CN -> Enter -> Set -> Enter -> repeat.
Verifies 3 entries are added and count updates accordingly.
"""


def steps(harness):
    harness.navigate("/ingestor-ids")
    harness.wait_for_visible("#cn-input")

    # Entry 1: Beast-Kin Ranger (FDN #100)
    harness.fill_by_selector("#cn-input", "100")
    harness.press_key("Enter")
    harness.fill_by_selector("#set-input", "fdn")
    harness.press_key("Enter")

    # Entry 2: Cathar Commando (FDN #139)
    harness.fill_by_selector("#cn-input", "139")
    harness.press_key("Enter")
    harness.fill_by_selector("#set-input", "fdn")
    harness.press_key("Enter")

    # Entry 3: Brazen Scourge (FDN #191)
    harness.fill_by_selector("#cn-input", "191")
    harness.press_key("Enter")
    harness.fill_by_selector("#set-input", "fdn")
    harness.press_key("Enter")

    # Verify 3 entries added
    harness.assert_text_present("Cards: 3")
    harness.assert_element_count("#entry-tbody tr", 3)

    harness.screenshot("final_state")
