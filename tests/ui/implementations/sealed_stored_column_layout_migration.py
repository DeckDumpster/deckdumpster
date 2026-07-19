"""
Hand-written implementation for sealed_stored_column_layout_migration.

A saved sealedCols layout predating the Market/Total split must gain the
Total column on next load, so users who customised their columns don't
silently lose the all-units figure when Market changed meaning.

Uses the harness.page.evaluate escape hatch to seed localStorage, following
the precedent in deck_detail_list_view_no_overflow.py. The migration runs at
module scope on page load, so the layout must be seeded before a fresh
navigation.
"""

LEGACY_COLS = '["qty","image","name","set","min_cost","market"]'


def steps(harness):
    # Establish the origin so localStorage is writable for this page.
    harness.navigate("/sealed")
    harness.wait_for_visible("table.sealed-table")

    # Seed a layout from before the split: it has 'market' but no 'total'.
    harness.page.evaluate(f"localStorage.setItem('sealedCols', '{LEGACY_COLS}')")

    # Reload so the module-scope migration runs against the stored layout.
    harness.navigate("/sealed")
    harness.wait_for_visible("table.sealed-table")

    # Visible outcome: Total is now a column, and the qty-6 Foundations row
    # shows its all-units figure. The legacy layout alone would show neither.
    harness.assert_text_present("Total")
    harness.assert_text_present("$21.00")

    # Stored outcome: 'total' was spliced in directly after 'market'.
    stored = harness.page.evaluate("localStorage.getItem('sealedCols')")
    assert stored is not None, "sealedCols was cleared instead of migrated"
    cols = [c.strip(' "') for c in stored.strip("[]").split(",")]
    assert "total" in cols, f"migration did not add 'total': {stored}"
    assert cols.index("total") == cols.index("market") + 1, (
        f"'total' should sit directly after 'market': {stored}"
    )
    # The pre-existing columns must survive the migration untouched.
    for key in ("qty", "image", "name", "set", "min_cost", "market"):
        assert key in cols, f"migration dropped '{key}': {stored}"

    harness.screenshot("final_state")
