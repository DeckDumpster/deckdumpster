"""
Hand-written implementation for sets_binder_first_add_creates_one_batch.

Browses spg without adding anything, then clicks one pip, and checks the
batches page: exactly one Binder batch, named for the set, holding one card.
"""

# The fixture ships two Corner batches, and the binder batch's NAME contains
# the word "binder" too — so the Binder batches are counted off the type badge
# element, whose text is exactly "Binder".
BINDER_BADGES = """() => [...document.querySelectorAll('.batch-type-badge')]
    .filter(b => b.textContent.trim() === 'Binder').length"""


def steps(harness):
    # start_page: /sets/spg?filter=need — auto-navigated by test runner.

    harness.wait_for_text("164 printings", timeout=5_000)

    # Nothing has been added, so there is no pass to review yet.
    harness.assert_hidden("#batch-link")

    # Browse: sort, search, and flip the direction. None of it posts anything,
    # so none of it may open a batch.
    harness.select_by_label("#sort", "Name")
    harness.fill_by_selector("#q", "Atlantis")
    harness.wait_for_text("1 printing", timeout=5_000)
    harness.fill_by_selector("#q", "")
    harness.wait_for_text("164 printings", timeout=5_000)
    harness.click_by_selector("#order")
    harness.wait_for_text("164 printings", timeout=5_000)

    harness.assert_hidden("#batch-link")

    # One click on one pip — the first add of the visit.
    harness.click_by_selector(".sheet-card:first-child .finish-pip:first-child")
    harness.wait_for_visible(
        ".sheet-card:first-child .finish-pip.filled", timeout=3_000
    )
    harness.assert_element_count(".pip-error", 0)

    # The link appears with the add that lands, not on page load: before that
    # there is no batch to link to.
    harness.wait_for_visible("#batch-link", timeout=3_000)
    href = harness.page.get_attribute("#batch-link", "href")
    assert href and href.startswith("/batches/"), f"Unexpected review link: {href!r}"

    harness.navigate("/batches")

    # Exactly one, from exactly one add. Browsing having opened batches of its
    # own would show up here as several.
    binder = harness.page.evaluate(BINDER_BADGES)
    assert binder == 1, f"Expected 1 Binder batch, found {binder}"

    harness.assert_text_present("Special Guests binder")
    harness.assert_text_present("1 card(s)")

    harness.screenshot("final_state")
