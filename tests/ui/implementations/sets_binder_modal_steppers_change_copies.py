"""
Hand-written implementation for sets_binder_modal_steppers_change_copies.

Opens the modal on an empty pocket, steps one finish up twice and back down
once, and checks the count, the tile behind the modal, and the header meter
after each step.
"""

NONFOIL_PLUS = '.binder-step[data-finish="nonfoil"][data-delta="1"]'
NONFOIL_MINUS = '.binder-step[data-finish="nonfoil"][data-delta="-1"]'
NONFOIL_COUNT = '.binder-count[data-finish="nonfoil"]'


def _count(harness):
    return harness.page.inner_text(NONFOIL_COUNT).strip()


def _pip(harness):
    """The nonfoil pip on the tile behind the modal, re-read every time: a step
    repaints the tile, which replaces the node."""
    el = harness.page.query_selector('.sheet-card .finish-pip[data-finish="nonfoil"]')
    return el.inner_text().strip(), el.get_attribute("class")


def steps(harness):
    # start_page: /sets/spg?q=Lord%20of%20Atlantis&filter=need — auto-navigated.

    harness.wait_for_text("1 printing", timeout=5_000)
    harness.assert_element_count(".sheet-card", 1)
    before = harness.page.inner_text("#meter-all-count").strip()
    assert before == "1 / 165", f"Unexpected starting meter: {before}"

    harness.click_by_selector(".sheet-card-img-wrap")
    harness.wait_for_visible(".card-modal-overlay.active", timeout=3_000)

    # One row per finish the printing exists in — nonfoil and foil here.
    harness.assert_element_count(".binder-finish", 2)
    assert _count(harness) == "0", f"Empty pocket did not start at 0: {_count(harness)}"

    # Nothing to take away yet, so neither minus is live.
    disabled = harness.page.eval_on_selector_all(
        '.binder-step[data-delta="-1"]', "els => els.map(e => e.disabled)")
    assert disabled == [True, True], f"A minus was live on an empty pocket: {disabled}"

    # First +: fills the pocket, so the meter moves by one printing.
    harness.click_by_selector(NONFOIL_PLUS)
    harness.wait_for_text("2 / 165", timeout=3_000)
    assert _count(harness) == "1", f"After one +: {_count(harness)}"

    # Second +: a second copy of a card already held fills no new pocket.
    harness.click_by_selector(NONFOIL_PLUS)
    harness.page.wait_for_function(
        f'document.querySelector(\'{NONFOIL_COUNT}\').textContent === "2"', timeout=3_000)
    assert harness.page.inner_text("#meter-all-count").strip() == "2 / 165", (
        "A second copy of the same printing moved the completion meter")

    # The tile behind the modal was repainted by the same step.
    label, cls = _pip(harness)
    assert label == "NF 2", f"Tile pip reads {label!r}, expected 'NF 2'"
    assert "filled" in cls, f"Tile pip is not filled: {cls}"

    harness.screenshot("after_two_adds")

    # Minus takes one back; the pocket stays filled, so the meter holds.
    harness.click_by_selector(NONFOIL_MINUS)
    harness.page.wait_for_function(
        f'document.querySelector(\'{NONFOIL_COUNT}\').textContent === "1"', timeout=5_000)
    assert harness.page.inner_text("#meter-all-count").strip() == "2 / 165", (
        "Removing one of two copies emptied the pocket")
    assert harness.page.inner_text(".binder-error").strip() == "", (
        "The step reported an error")

    label, cls = _pip(harness)
    assert label == "NF", f"Tile pip reads {label!r}, expected 'NF' at one copy"
    assert "filled" in cls, f"Tile pip is not filled: {cls}"

    harness.screenshot("final_state")
