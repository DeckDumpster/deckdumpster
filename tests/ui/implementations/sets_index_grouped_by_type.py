"""
Hand-written implementation for sets_index_grouped_by_type.

Pins the two orderings the page depends on the API for — groups newest-first,
and sets newest-first inside a group — plus the per-tile contents: keyrune
symbol, code and date, and the link to the binder page.
"""


def steps(harness):
    # Every cached set has a tile, and the 5 set_types are 5 blocks.
    harness.assert_element_count("a.set-tile", 18)
    harness.assert_element_count("section.set-group", 5)
    harness.assert_visible("#sets-count")
    harness.assert_text_present("18 sets")

    # /api/sets/index comes back newest release first and the page groups it
    # preserving first appearance, so the group holding the newest set leads.
    # Lorwyn Eclipsed (2026-01-23) is an expansion, so Expansion is first.
    harness.assert_element_count(
        "#sets-body > section.set-group:first-child[data-set-type='expansion']", 1
    )
    # And the order survives inside the group: ecl is its first tile.
    harness.assert_element_count(
        "section.set-group[data-set-type='expansion'] a.set-tile:first-child[href='/sets/ecl']",
        1,
    )

    # The tile is a link to the binder page, and carries the set's own keyrune
    # glyph — the class is what selects the glyph out of the font.
    harness.assert_visible("a.set-tile[href='/sets/ecl'] i.ss.ss-ecl.ss-2x")
    harness.assert_text_present("Lorwyn Eclipsed")
    harness.assert_text_present("ECL · 2026-01-23")

    harness.screenshot("final_state")
