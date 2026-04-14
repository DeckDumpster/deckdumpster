"""
Hand-written implementation for collection_modal_overlays_sticky_header.

Proves the card detail modal (z-index 100) still visually covers the
sticky header (z-index 50). Uses document.elementFromPoint at a
coordinate inside the header region to verify that what's at that
point after the modal opens is part of the modal, not the header.
"""


def steps(harness):
    # start_page: /collection — auto-navigated by test runner.
    harness.wait_for_visible("#search-input")
    harness.wait_for_visible("tr[data-idx]")

    # Switch to grid view before clicking a card: table rows center-click
    # often lands on a [data-filter-type] cell (mana cost, color pill, etc.)
    # which triggers the filter path instead of the modal. Grid cards are
    # a single clickable region with a cleaner target.
    harness.click_by_selector("#view-grid-btn")
    harness.click_by_selector(".sheet-card[data-idx]")
    harness.wait_for_visible("#card-modal-overlay.active")

    # What element sits at (viewportCenterX, 20)? y=20 is inside the
    # header's vertical band. With modal z-index 100 above header's 50,
    # it must be something inside #card-modal-overlay.
    result = harness.page.evaluate("""() => {
      const el = document.elementFromPoint(window.innerWidth / 2, 20);
      if (!el) return { tag: null, underModal: false };
      return {
        tag: el.tagName.toLowerCase(),
        underModal: el.closest('#card-modal-overlay') !== null,
        inHeader: el.closest('header') !== null,
      };
    }""")
    assert result["underModal"], (
        f"Expected element at (centerX, 20) to be inside #card-modal-overlay, "
        f"but got <{result['tag']}> (inHeader={result.get('inHeader')}). "
        f"The sticky header is bleeding through the modal — z-index stack regression."
    )

    harness.screenshot("final_state")
