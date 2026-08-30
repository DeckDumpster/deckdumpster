"""
Hand-written implementation for collection_price_chart.

Seeds price data via harness.db_exec, opens the card modal for a card with
price data, and verifies the price chart appears. Then opens a card
with no price data and confirms the chart section is hidden.
"""


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
    # Switch to grid view and click the card.
    harness.click_by_selector("#view-grid-btn")
    harness.click_by_selector(".sheet-card[data-idx]")
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
    # Wait for the card grid to update — exactly 1 entry for Orazca.
    harness.wait_for_text("1 card", timeout=5_000)
    harness.click_by_selector(".sheet-card[data-idx]")
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    # Scroll down — chart section should not be visible.
    harness.page.evaluate("document.querySelector('#modal-details').scrollTop = 9999")
    # 2_000 here (an outlier against every other wait in this file) flaked
    # under CI load: the previous card's chart section takes longer than that
    # to finish hiding after the modal reopens on a busy runner. 5_000 matches
    # the modal-close wait above it.
    harness.wait_for_hidden(".price-chart-section.visible", timeout=5_000)
    harness.screenshot("final_state")
