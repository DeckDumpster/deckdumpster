"""
Hand-written implementation for sets_index_grouped_by_type.

Pins the ordering the page depends on the API for — sets newest-first inside a
group — plus the per-tile contents: keyrune symbol, code and date, and the link
to the binder page.

The group order is `SET_TYPE_RANK` in sets.js, and this fixture cannot see it:
its five types come out in the same sequence whether the rank is applied or the
response's own release order is. `tests/test_sets_page.py` pins the rank against
a synthetic payload, which is the only place the difference shows.
"""


def steps(harness):
    # Every cached set has a tile, and the 5 set_types are 5 blocks.
    harness.assert_element_count("a.set-tile", 18)
    harness.assert_element_count("section.set-group", 5)
    harness.assert_visible("#sets-count")
    harness.assert_text_present("18 sets")

    # Expansion is the first block — see the module docstring for why this
    # assertion alone does not prove the group order is the curated one.
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
