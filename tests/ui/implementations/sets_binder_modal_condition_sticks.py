"""
Hand-written implementation for sets_binder_modal_condition_sticks.

Sets the condition in one card's modal, closes it, opens a different card, and
checks the select came back carrying the same choice.
"""

CONDITIONS = ["Near Mint", "Lightly Played", "Moderately Played",
              "Heavily Played", "Damaged"]


def _open_tile(harness, index):
    """Open the modal on the nth tile (0-based) and return its heading."""
    harness.page.query_selector_all(".sheet-card .sheet-card-img-wrap")[index].click()
    harness.wait_for_visible(".card-modal-overlay.active", timeout=3_000)
    harness.wait_for_visible("#binder-condition", timeout=3_000)
    return harness.page.inner_text(".card-modal-details h2").strip()


def steps(harness):
    # start_page: /sets/spg?filter=need — auto-navigated by the test runner.

    harness.wait_for_text("164 printings", timeout=5_000)

    first = _open_tile(harness, 0)

    # The five the schema accepts, no more and no fewer.
    options = harness.page.eval_on_selector(
        "#binder-condition", "el => Array.from(el.options).map(o => o.value)")
    assert options == CONDITIONS, f"Condition options are {options}"
    assert harness.page.input_value("#binder-condition") == "Near Mint", (
        "A fresh visit did not start at Near Mint")

    harness.select_by_label("#binder-condition", "Lightly Played")
    harness.screenshot("condition_set_on_first_card")

    harness.click_by_selector(".card-modal-close")
    harness.wait_for_hidden(".card-modal-overlay.active", timeout=3_000)

    # A different card — the select is rebuilt from scratch, so a value here can
    # only have come from page state.
    second = _open_tile(harness, 1)
    assert second != first, f"Both clicks opened the same card: {second!r}"

    still = harness.page.input_value("#binder-condition")
    assert still == "Lightly Played", (
        f"Condition did not stick across cards: {still!r} on {second!r}")

    harness.screenshot("final_state")
