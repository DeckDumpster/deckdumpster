"""
Hand-written implementation for sets_binder_image_opens_modal_not_add.

Clicks the art on an empty pocket and verifies the modal opens while the
collection is untouched.
"""


def steps(harness):
    # start_page: /sets/spg?filter=need — auto-navigated by test runner.

    harness.wait_for_text("164 printings", timeout=5_000)

    # Every pocket on this view is empty, so a filled pip afterwards would mean
    # the art added a copy.
    harness.assert_element_count(".finish-pip.filled", 0)
    before = harness.page.inner_text("#meter-all-count").strip()
    assert before == "1 / 165", f"Unexpected starting meter: {before}"

    alt = harness.page.get_attribute(".sheet-card .sheet-card-img-wrap img", "alt")

    # The art, not a pip: the pips are separate buttons rendered outside this
    # element precisely so the two targets cannot be confused.
    harness.click_by_selector(".sheet-card-img-wrap")

    harness.wait_for_visible(".card-modal-overlay.active", timeout=3_000)
    heading = harness.page.inner_text(".card-modal-details h2").strip()
    assert heading, "Modal opened with no card heading"
    assert heading.split(" // ")[0] in (alt or heading), (
        f"Modal shows {heading!r}, expected the clicked card {alt!r}"
    )

    # Nothing was added.
    harness.assert_element_count(".finish-pip.filled", 0)
    after = harness.page.inner_text("#meter-all-count").strip()
    assert after == before, f"Opening the modal changed the meter: {before} -> {after}"

    harness.screenshot("final_state")
