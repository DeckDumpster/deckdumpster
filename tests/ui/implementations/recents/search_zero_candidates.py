"""
Hand-written implementation for search_zero_candidates.

The Claude harness struggles with this scenario because:
1. The card thumbnails are small photos (not text buttons) — vision model
   clicks the wrong elements or triggers reprocessing.
2. The search input is PRE-FILLED and just needs Enter — there's no harness
   tool for "press key" so the generated code always falls back to fill().
3. The accordion opens below the card row, changing layout — vision model
   gets confused by the DOM shift.

Flow verified via manual Playwright walkthrough (2026-03-01):
  /recent loads with 5 cards, default 2h pill shows all.
  Llanowar Elves has 1 disambiguated entry with sid=null and 0 candidates.
  Click card → accordion opens with pre-filled search "Llanowar Elves".
  Press Enter → POST /api/ingest2/search-card → 6 FDN candidates appear.
  Click first candidate → green border.
  Click "Batch Ingest" → success toast.
"""


def steps(harness):
    # The Llanowar Elves card label is visible text below the thumbnail.
    harness.click_by_text("Llanowar Elves")
    # The accordion search input is pre-filled with "Llanowar Elves".
    # Just press Enter to trigger the search.
    harness.press_key("Enter", selector='[id^="acc-search-input-"]')
    # Click the first candidate card to select it.
    harness.click_by_selector(".acc-candidates .acc-candidate:first-child")
    # Ingest all selected cards.
    harness.click_by_text("Batch Ingest")
    harness.screenshot("final_state")
