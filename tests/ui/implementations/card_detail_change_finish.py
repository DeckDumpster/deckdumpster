"""
Hand-written implementation for card_detail_change_finish.

Switches a copy's recorded finish from nonfoil to foil via the inline
select on the card detail page and verifies the page reload picks up
the new finish in the copy header label.
"""


def steps(harness):
    # start_page: /card/fdn/100 — Beast-Kin Ranger, one owned copy id=3,
    # currently nonfoil. Printing supports ["nonfoil", "foil"] so the
    # finish select is rendered.
    harness.wait_for_text("Beast-Kin Ranger")
    harness.wait_for_visible(".copy-section")
    # The copy starts as nonfoil — verified via the header text.
    harness.assert_text_present("Nonfoil Near Mint")
    harness.screenshot("before_change")
    # Flip finish to foil via the inline select. The handler PUTs
    # /api/collection/3 with {finish: "foil"} and reloads the page.
    harness.select_by_label(".change-finish-select", "Foil")
    # After reload the copy header should now read "Foil Near Mint".
    harness.wait_for_text("Foil Near Mint", timeout=5_000)
    harness.assert_visible(".copy-section")
    harness.assert_text_absent("Nonfoil Near Mint")
    harness.screenshot("final_state")
