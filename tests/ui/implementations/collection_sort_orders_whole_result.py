"""
Hand-written implementation for collection_sort_orders_whole_result.

Reversing the sort on a windowed result must reorder all 7,603 rows, not the
250 the browser happens to be holding.
"""


def steps(harness):
    harness.navigate("/collection?q=is%3Aunowned")
    harness.wait_for_visible("#vtbody tr[data-idx]:not([data-pending])", timeout=15_000)

    # Ascending by name: the result opens at the top of the alphabet.
    harness.assert_text_present("A Killer Among Us")
    harness.screenshot("ascending")

    # Toggle to descending.
    harness.click_by_selector(".collection-table th[data-col='name']")
    harness.wait_for_visible("#vtbody tr[data-idx]:not([data-pending])", timeout=15_000)

    # The end of the alphabet is now first. Sorting the loaded window instead
    # of the result would have left another "A..." name here.
    harness.wait_for_text("Zur's Weirding", timeout=15_000)
    first_row = harness.page.eval_on_selector(
        "#vtbody tr[data-idx] .card-name", "el => el.textContent.trim()"
    )
    assert first_row == "Zur's Weirding", f"expected the last card of the result first, got {first_row!r}"

    # Re-sorting kept the same result, so the count is unchanged.
    harness.assert_text_present("7,603 results")

    harness.screenshot("final_state")
