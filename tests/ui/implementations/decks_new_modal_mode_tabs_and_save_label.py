"""
Hand-written implementation for decks_new_modal_mode_tabs_and_save_label.

Opens the New Deck modal, asserts Blank-mode defaults, switches to the
Preconstructed tab, asserts the field swap and the Save→Import label flip,
then switches back to Blank to confirm the original state is restored.
"""


def steps(harness):
    # Open the New Deck modal.
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=1000)
    # Blank is the default tab — Name input + "Create" button should be visible.
    harness.assert_visible('.mode-tab[data-mode="blank"].active')
    harness.assert_visible("#mode-blank.active")
    harness.assert_visible('input[placeholder="My Commander Deck"]')
    harness.assert_text_present("Create")
    # Switch to the Preconstructed tab.
    harness.click_by_selector('.mode-tab[data-mode="precon"]')
    # Precon section is now visible; the blank section's Name input is gone.
    harness.wait_for_visible("#mode-precon.active", timeout=1000)
    harness.assert_visible("#f-precon-set")
    harness.assert_hidden("#mode-blank")
    # Save button text flipped to "Import".
    harness.assert_text_present("Import")
    # Switch back to Blank — Name returns, button reads "Create" again.
    harness.click_by_selector('.mode-tab[data-mode="blank"]')
    harness.wait_for_visible("#mode-blank.active", timeout=1000)
    harness.assert_visible('input[placeholder="My Commander Deck"]')
    harness.assert_hidden("#mode-precon")
    harness.assert_text_present("Create")
    harness.screenshot("final_state")
