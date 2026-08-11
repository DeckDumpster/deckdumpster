"""
Hand-written implementation for collection_stats_modal_states_loaded_coverage.

The stats modal computes from the rows in memory, so when those are only part
of the result it has to say so — and when they are all of it, it must not.
"""


def steps(harness):
    # A result far larger than one page: the caveat belongs here.
    harness.navigate("/collection?q=is%3Aunowned")
    harness.wait_for_visible("#vtbody tr[data-idx]:not([data-pending])", timeout=15_000)
    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=10_000)

    # Assert the invariant tail only — the number of rows loaded depends on
    # how far the prefetch got.
    harness.assert_text_present("of 7,603 matches loaded so far")
    harness.screenshot("windowed_result_states_coverage")

    # The owned collection is 43 rows and fits in a single page, so the
    # figures are the whole result and the caveat must not appear.
    harness.navigate("/collection")
    harness.wait_for_visible("#vtbody tr[data-idx]:not([data-pending])", timeout=15_000)
    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=10_000)
    harness.assert_text_absent("loaded so far")

    harness.screenshot("final_state")
