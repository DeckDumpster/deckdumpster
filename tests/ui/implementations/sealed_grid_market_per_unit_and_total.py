"""
Hand-written implementation for sealed_grid_market_per_unit_and_total.

Verifies grid tiles show a per-unit "<price>/ea mkt" line, and that the
subordinate "<price> total" line appears only for entries with quantity > 1.

Read-only against fixture data.
"""


def steps(harness):
    # Switch to grid view.
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_visible(".sheet-card")

    # The qty-6 Foundations tile carries both lines: per-unit and all-units.
    harness.assert_text_present("$3.50/ea mkt")
    harness.assert_text_present("$21.00 total")

    # A quantity-1 product shows the per-unit line only. Its total would just
    # repeat $99.50, so no total line is rendered for it.
    harness.assert_text_present("$99.50/ea mkt")
    harness.assert_text_absent("$99.50 total")

    # Exactly two visible entries have quantity > 1 (Foundations packs at 6 and
    # Modern Horizons 3 packs at 3), so exactly two tiles carry a total line.
    # The 'opened' Bloomburrow packs are hidden by the default filter.
    harness.assert_element_count(".market-total", 2)

    harness.screenshot("final_state")
