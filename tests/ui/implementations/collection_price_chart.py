"""
Hand-written implementation for collection_price_chart.

Seeds price data via harness.db_exec, opens the card modal for a card with
price data, and verifies the price chart appears. Then opens a card
with no price data and confirms the chart section is hidden.
"""

# The two demo cards this scenario turns on: blb/124 has the seeded price
# history, lci/68 has none. A tile renders the card name as its image `alt`,
# which is the only per-card handle the grid exposes.
PRICED = "Artist's Talent"
UNPRICED = "Orazca Puzzle-Door"


def steps(harness):
    # Seed price data into the database inside the container.
    seed_script = (
        "import sqlite3, datetime as dt\n"
        "conn = sqlite3.connect('/data/collection.sqlite')\n"
        "conn.execute('''\n"
        "  INSERT OR IGNORE INTO prices\n"
        "  (set_code, collector_number, source, price_type, price, observed_at)\n"
        "  VALUES\n"
        "  ('blb','124','tcgplayer','normal',8.50,date('now','-60 days')),\n"
        "  ('blb','124','tcgplayer','normal',9.00,date('now','-45 days')),\n"
        "  ('blb','124','tcgplayer','normal',10.00,date('now','-30 days')),\n"
        "  ('blb','124','tcgplayer','normal',10.50,date('now','-15 days')),\n"
        "  ('blb','124','tcgplayer','normal',10.46,date('now'))\n"
        "''')\n"
        "conn.commit()\n"
        "conn.close()\n"
    )
    harness.db_exec(seed_script)

    # start_page: /collection — auto-navigated by test runner.
    # Search for Artist's Talent (blb/124) which has seeded price data.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Artist's Talent")
    harness.wait_for_visible("tr[data-idx]", timeout=15_000)
    # Switch to grid view and click the card by name. `.sheet-card[data-idx]`
    # would click whichever tile happens to be first, which before this search's
    # rows land is a card with no price history.
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_attached(f'.sheet-card img[alt="{PRICED}"]', timeout=15_000)
    harness.click_by_selector(f'.sheet-card:has(img[alt="{PRICED}"])')
    # Wait for modal to appear.
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    # Scroll down in the modal to see the price chart.
    harness.page.evaluate("document.querySelector('#modal-details').scrollTop = 9999")
    harness.page.wait_for_timeout(500)
    # The price chart section should become visible.
    harness.wait_for_visible(".price-chart-section.visible", timeout=10_000)
    harness.assert_visible("#price-chart-canvas")
    harness.screenshot("chart_visible")

    # Close the modal.
    harness.click_by_selector("#modal-close")
    harness.wait_for_hidden("#card-modal-overlay.active", timeout=5_000)

    # Now open a card with no price data to verify chart is hidden. Typing the
    # new term directly is deliberate: `fill` replaces the whole value and fires
    # the input event either way, so clearing first only bought a second
    # debounced re-fetch that re-rendered the entire 43-card fixture — and the
    # next keystroke then landed on a busy main thread (measured 696 ms against
    # this suite's 500 ms interaction budget). The delay used to be hidden by
    # the `podman ps` scan this scenario ran to find its own container (de-1zq).
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Orazca")
    # Wait for the *new* card, not for a count. Both searches match exactly one
    # entry, so "1 card" was already on the page from the previous search and
    # the wait returned without the grid having changed at all — measured: the
    # text is present before the fill is even typed. The click then landed on
    # the priced card's own tile, its modal re-opened with the chart still
    # visible, and the assertion below failed 5 s later on a page that had never
    # moved on (de-bj7). Naming the card is what makes this a barrier.
    harness.wait_for_attached(f'.sheet-card img[alt="{UNPRICED}"]', timeout=5_000)
    harness.click_by_selector(f'.sheet-card:has(img[alt="{UNPRICED}"])')
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    # Scroll down — chart section should not be visible.
    harness.page.evaluate("document.querySelector('#modal-details').scrollTop = 9999")
    harness.wait_for_hidden(".price-chart-section.visible", timeout=2_000)
    harness.screenshot("final_state")
