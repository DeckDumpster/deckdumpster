"""
Hand-written implementation for sets_binder_second_add_joins_the_batch.

Two pip adds in one page visit, on two different tiles, and one batch holding
both -- not one batch per click.
"""

BINDER_BADGES = """() => [...document.querySelectorAll('.batch-type-badge')]
    .filter(b => b.textContent.trim() === 'Binder').length"""


def steps(harness):
    # start_page: /sets/spg?filter=need — auto-navigated by test runner.

    harness.wait_for_text("164 printings", timeout=5_000)
    harness.assert_hidden("#batch-link")

    # First add: creates the visit's batch.
    harness.click_by_selector(".sheet-card:nth-child(1) .finish-pip:first-child")
    harness.wait_for_visible("#batch-link", timeout=3_000)
    first = harness.page.get_attribute("#batch-link", "href")

    # Second add, a different card, same visit — no navigation in between,
    # because the visit is what the batch is scoped to.
    harness.click_by_selector(".sheet-card:nth-child(2) .finish-pip:first-child")
    harness.wait_for_visible(
        ".sheet-card:nth-child(2) .finish-pip.filled", timeout=3_000
    )
    harness.assert_element_count(".pip-error", 0)
    second = harness.page.get_attribute("#batch-link", "href")

    assert second == first, (
        f"The second add opened another batch: {first} -> {second}"
    )

    harness.navigate("/batches")

    binder = harness.page.evaluate(BINDER_BADGES)
    assert binder == 1, f"Expected 1 Binder batch for the pass, found {binder}"

    harness.assert_text_present("Special Guests binder")
    harness.assert_text_present("2 card(s)")

    harness.screenshot("final_state")
