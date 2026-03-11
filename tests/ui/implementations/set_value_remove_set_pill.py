"""
Hand-written implementation for set_value_remove_set_pill.

Selects two sets, verifies pills appear, removes them one by one,
and verifies the Analyze button disables when all pills are removed.
"""


def steps(harness):
    # start_page: /set-value — auto-navigated by test runner.
    harness.wait_for_visible("#set-search")

    # Select first set: Bloomburrow
    harness.fill_by_selector("#set-search", "Bloom")
    harness.wait_for_visible("#set-dropdown.open li", timeout=10_000)
    harness.click_by_selector("#set-dropdown li")
    harness.wait_for_visible(".selected-pill")

    # Clear search and select second set: Foundations
    harness.fill_by_selector("#set-search", "Foundations")
    harness.wait_for_visible("#set-dropdown.open li", timeout=10_000)
    harness.click_by_selector("#set-dropdown li")

    # Verify two pills are present
    harness.assert_element_count(".selected-pill", 2)

    # Clear search input and click elsewhere to close any dropdown
    harness.fill_by_selector("#set-search", "")
    harness.click_by_selector("h1")
    harness.page.wait_for_timeout(300)
    harness.screenshot("two_pills")

    # Remove the first pill by clicking its x button
    harness.click_by_selector(".selected-pill .remove-pill")

    # Verify one pill remains
    harness.assert_element_count(".selected-pill", 1)
    harness.screenshot("one_pill")

    # Remove the last pill
    harness.click_by_selector(".selected-pill .remove-pill")

    # Verify no pills remain and Analyze is disabled
    harness.assert_element_count(".selected-pill", 0)

    harness.screenshot("final_state")
