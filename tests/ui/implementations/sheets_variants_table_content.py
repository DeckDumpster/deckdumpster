"""
Hand-written implementation for sheets_variants_table_content.

Loads BLB play sheets and verifies the Variants section contains a
table with probability values and pill-shaped sheet labels.
"""


def steps(harness):
    # Navigate directly to BLB play via deep link
    harness.navigate("/sheets#set=blb&product=play")

    # Wait for sections to render
    harness.wait_for_visible(".section-header")

    # Variants section is expanded by default -- verify table is visible
    harness.assert_visible(".variants-table")

    # Verify variant pill labels exist inside the table
    harness.assert_visible(".variant-pill")

    # Verify probability percentages are shown (table has % values)
    harness.assert_text_present("%")

    # Verify status text shows sheet count
    harness.assert_text_present("8 sheets")

    harness.screenshot("final_state")
