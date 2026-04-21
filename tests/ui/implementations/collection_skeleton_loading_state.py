"""
Hand-written implementation for collection_skeleton_loading_state.

Intercepts the collection API to delay it, then verifies the skeleton
table with shimmer placeholders appears while loading.
"""
import time


def steps(harness):
    # Delay the collection API so the skeleton is visible
    def delay_response(route):
        time.sleep(3)
        route.continue_()

    harness.page.route("**/api/collection**", delay_response)

    # Navigate without waiting for networkidle (skeleton is pre-networkidle)
    harness.page.goto(
        f"{harness.base_url}/collection", wait_until="domcontentloaded", timeout=10_000
    )

    # Wait for the skeleton table to appear (renderSkeleton creates .skeleton-row)
    harness.page.wait_for_selector(".skeleton-row", timeout=5_000)

    skeleton_rows = harness.page.locator(".skeleton-row").count()
    assert skeleton_rows > 0, "Expected skeleton rows while loading"

    skeleton_cells = harness.page.locator(".skeleton-cell").count()
    assert skeleton_cells > 0, "Expected skeleton cells while loading"

    # Verify column headers are in the skeleton
    harness.assert_visible(".collection-table thead")
    harness.screenshot("skeleton_visible")

    # Wait for real data to replace the skeleton
    harness.wait_for_visible("#vtbody tr[data-idx]", timeout=10_000)

    # Verify skeleton is gone, replaced by real rows
    final_skeleton = harness.page.locator(".skeleton-row").count()
    assert final_skeleton == 0, "Skeleton rows should be gone after data loads"

    harness.screenshot("final_state")
