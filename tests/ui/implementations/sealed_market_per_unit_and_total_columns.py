"""
Hand-written implementation for sealed_market_per_unit_and_total_columns.

Verifies the table's Market column is per-unit and the new Total column
carries quantity x market price, using the fixture's quantity-6 Foundations
Collector Booster Pack row ($3.50 each, $21.00 total).

Read-only: it must not mutate the qty-6 entry, which is shared with
sealed_partial_dispose_qty.
"""


def steps(harness):
    # Table view is the default, but assert it explicitly so the scenario does
    # not depend on leftover view state from another test.
    harness.click_by_selector("#view-table-btn")
    harness.wait_for_visible("table.sealed-table")

    # Both columns are default-on, so they render without touching the drawer.
    harness.assert_text_present("Market")
    harness.assert_text_present("Total")

    # The qty-6 Foundations row: per-unit market price and the all-units total
    # are different values, which is the whole point of the split.
    harness.wait_for_text("Foundations")
    harness.assert_text_present("$3.50")
    harness.assert_text_present("$21.00")

    # Min Cost is also per-unit, so it sits alongside Market comparably.
    harness.assert_text_present("$4.50")

    harness.screenshot("final_state")
