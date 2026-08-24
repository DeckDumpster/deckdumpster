"""
Hand-written implementation for sheets_card_badge_link_no_zoom.

Loads BLB play sheets via the deep link, expands a section, and clicks a
card's SF/CK price badge — a link inside the tile whose own click handler
opens the zoom overlay. Only the link should act.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for the play sheets to render. "8 sheets" rather than
    # .section-header because the deep link loads two products and both paint
    # section headers; only the count tells them apart. 5 s because this is
    # the page load, not an interaction — see sheets_card_zoom_overlay.
    harness.wait_for_text("8 sheets", timeout=5_000)

    # Expand the "Common" section to reveal cards (exact match)
    harness.click_by_text("Common", exact=True)
    harness.wait_for_visible(".section.open .sheet-card", timeout=500)

    # The price badges are links; wait for one before clicking it
    harness.wait_for_visible(".section.open .sheet-card a.badge.link", timeout=500)

    # Click the badge. It is target="_blank", so the vendor page opens in a
    # background tab and this page stays on /sheets.
    harness.click_by_selector(".section.open .sheet-card a.badge.link")

    # The tile's click handler must not have fired: no zoom overlay.
    harness.assert_hidden("#zoom-overlay.active")

    harness.screenshot("final_state")
