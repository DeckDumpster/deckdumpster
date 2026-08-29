"""
Hand-written implementation for card_detail_price_chart.

Seeds price data via harness.db_exec, re-navigates to load the chart,
verifies range pills, and switches to a different range.
"""


def steps(harness):
    # start_page: /card/blb/124 — auto-navigated by test runner.
    harness.wait_for_text("Artist's Talent")

    # Seed price data into the database via python inside the container
    # (the sqlite3 CLI is not installed in the image).
    python_script = (
        "import sqlite3, datetime as dt, os; "
        "db = os.environ.get('MTGC_SHARED_DB', '/data/collection.sqlite'); "
        "conn = sqlite3.connect(db); "
        "rows = ["
        "('blb','124','tcgplayer','normal',8.50,(dt.date.today()-dt.timedelta(days=60)).isoformat()),"
        "('blb','124','tcgplayer','normal',9.00,(dt.date.today()-dt.timedelta(days=45)).isoformat()),"
        "('blb','124','tcgplayer','normal',10.00,(dt.date.today()-dt.timedelta(days=30)).isoformat()),"
        "('blb','124','tcgplayer','normal',10.50,(dt.date.today()-dt.timedelta(days=15)).isoformat()),"
        "('blb','124','tcgplayer','normal',10.46,dt.date.today().isoformat())"
        "]; "
        "conn.executemany('INSERT OR IGNORE INTO prices "
        "(set_code,collector_number,source,price_type,price,observed_at) "
        "VALUES (?,?,?,?,?,?)', rows); "
        "conn.execute('INSERT OR REPLACE INTO latest_prices "
        "(set_code,collector_number,source,price_type,price,observed_at) "
        "VALUES (?,?,?,?,?,?)', rows[-1]); "
        "conn.commit(); conn.close()"
    )
    harness.db_exec(python_script)

    # Re-navigate so the chart picks up the seeded data.
    harness.navigate("/card/blb/124")
    harness.wait_for_text("Artist's Talent")

    # The price chart section should become visible (chart.js render takes time).
    harness.wait_for_visible(".price-chart-section.visible", timeout=2000)
    # Canvas element should exist.
    harness.assert_visible("#price-chart-canvas")
    # A range pill should be active.
    harness.assert_visible(".price-range-pill.active")
    harness.screenshot("chart_visible")

    # Click the "ALL" range pill.
    harness.click_by_selector('.price-range-pill[data-range="0"]')
    # ALL pill should now be active.
    harness.assert_visible('.price-range-pill[data-range="0"].active')
    harness.screenshot("final_state")
