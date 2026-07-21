"""
Hand-written implementation for sealed_null_market_price_blank.

The fixture deliberately leaves the Duskmourn: House of Horror Bundle
unpriced. Its Market and Total cells must render empty rather than $0.00,
in both table and grid view.

Read-only against fixture data.
"""


def steps(harness):
    # Table view first.
    harness.click_by_selector("#view-table-btn")
    harness.wait_for_visible("table.sealed-table")

    # The unpriced row is present — its purchase price still shows.
    harness.assert_text_present("$40.00")

    # Null prices render as an empty string. Zero is a meaningful price, so
    # substituting it would be wrong; no entry on this page is worth $0.00.
    harness.assert_text_absent("$0.00")

    # Same guarantee in grid view, where the tile omits the market lines
    # entirely rather than rendering a zero.
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_visible(".sheet-card")
    harness.assert_text_absent("$0.00")
    harness.assert_text_absent("$0.00/ea mkt")

    harness.screenshot("final_state")
