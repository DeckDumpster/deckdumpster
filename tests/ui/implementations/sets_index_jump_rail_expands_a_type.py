"""
Hand-written implementation for sets_index_jump_rail_expands_a_type.

Clicking a rail row opens the block it names.

The scroll half of the jump is smooth and the harness has no scroll-position
assertion, so it is pinned in tests/test_sets_page.py; what is checked here is
that the row reached a folded block and opened it.
"""

DUEL_DECK_ROW = "#sets-rail .rail-row[data-set-type='duel_deck']"


def steps(harness):
    # One row per set type the fixture has cached, not one per SET_TYPE_RANK
    # entry — a row for a type with no sets would jump nowhere.
    harness.assert_visible("#sets-rail .rail-title")
    harness.assert_element_count("#sets-rail .rail-row", 5)
    harness.assert_element_count("#sets-rail .rail-row .rail-count", 5)

    # Duel Deck is folded shut, and its row is the way in.
    harness.assert_visible(DUEL_DECK_ROW)
    harness.assert_hidden("section[data-set-type='duel_deck'] .set-grid")

    harness.click_by_selector(DUEL_DECK_ROW)

    harness.assert_visible("section[data-set-type='duel_deck'] .set-grid")
    harness.assert_visible("a.set-tile[href='/sets/ddh']")

    # A row is a label and a count and nothing else: 13 of 24 MTG set types
    # hold something, so an ownership dot per row would be noise, not signal.
    harness.assert_element_count("#sets-rail .rail-row > *", 10)

    harness.screenshot("final_state")
