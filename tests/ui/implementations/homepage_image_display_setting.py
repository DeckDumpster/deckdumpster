"""
Hand-written implementation for homepage_image_display_setting.
Verifies Image Display pills reflect saved state, toggles between Crop
and Contain, checks the Saved indicator, and confirms persistence on reload.
"""


def steps(harness):
    # Navigate to homepage
    harness.navigate("/")

    # Wait for settings to load (Crop pill becomes active by default)
    harness.wait_for_visible("#image-display-pills .pill.active")

    # Verify Crop is the active pill (default setting)
    harness.assert_visible("#image-display-pills .pill[data-value='crop'].active")

    # Click Contain pill to switch
    harness.click_by_selector("#image-display-pills .pill[data-value='contain']")

    # Verify Contain is now active
    harness.assert_visible("#image-display-pills .pill[data-value='contain'].active")

    # Verify Saved indicator appears
    harness.wait_for_visible("#save-status.visible")

    # Reload page to verify persistence
    harness.navigate("/")
    harness.wait_for_visible("#image-display-pills .pill.active")

    # Verify Contain is still active after reload
    harness.assert_visible("#image-display-pills .pill[data-value='contain'].active")

    # Restore default: click Crop pill
    harness.click_by_selector("#image-display-pills .pill[data-value='crop']")
    harness.wait_for_visible("#save-status.visible")

    harness.screenshot("final_state")
