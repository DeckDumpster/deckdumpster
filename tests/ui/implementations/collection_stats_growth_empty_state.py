"""
Hand-written implementation for collection_stats_growth_empty_state.

Filters to is:unowned — which the growth endpoint short-circuits to an empty
series — and verifies the chart area degrades to its placeholder message while
the rest of the stats modal still renders. No seeding required.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15_000)
    harness.wait_for_text("45 cards", timeout=15_000)

    # is:unowned flips the query to a LEFT JOIN against printings. Unowned rows
    # carry qty 0, so updateStatusText() switches the noun from "cards" to
    # "results" — asserting on the noun keeps this independent of the fixture's
    # exact printing count.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "is:unowned")
    harness.wait_for_text("results", timeout=15_000)
    harness.assert_text_absent("45 cards")
    harness.screenshot("unowned_filter")

    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=10_000)

    # The growth section renders its placeholder rather than a chart.
    harness.assert_text_present("Growth over time")
    harness.wait_for_visible("#growth-chart-wrap .growth-empty", timeout=10_000)
    harness.assert_text_present("No acquisition history for the current filter")
    harness.assert_hidden("#growth-chart-canvas")

    # The empty state is scoped to the chart — the rest of the modal is intact.
    harness.assert_text_present("Entries (rows)")
    harness.assert_text_present("Distinct printings")

    harness.screenshot("final_state")
