"""
Hand-written implementation for sheets_variants_table_content.

Loads BLB play sheets and verifies the Variants section contains a
table with probability values and pill-shaped sheet labels.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for the play render before asserting anything. The deep link loads
    # two products: loadProducts() auto-checks the first one (collector,
    # 6 sheets) and fires a sheet load for it, then setSelectedProduct()
    # switches to play and fires a second. Both paint .variants-table and
    # .variant-pill, so an assertion made before this wait can be satisfied by
    # collector's render. #status is written last, after the ~1000-card section
    # loop, so the count is the only thing that tells the two renders apart.
    # 5 s (as in the sibling sheets scenarios) because this is the page load,
    # not an interaction — every assertion below keeps the 500 ms budget.
    harness.wait_for_text("8 sheets", timeout=5_000)

    # Variants section is expanded by default -- verify table is visible
    harness.assert_visible(".variants-table")

    # Verify variant pill labels exist inside the table
    harness.assert_visible(".variant-pill")

    # Verify probability percentages are shown (table has % values)
    harness.assert_text_present("%")

    harness.screenshot("final_state")
