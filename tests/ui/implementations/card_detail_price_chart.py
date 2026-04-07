"""
Hand-written implementation for card_detail_price_chart.

Seeds price data via podman exec, re-navigates to load the chart,
verifies range pills, and switches to a different range.
"""

import subprocess


def _find_container(base_url):
    """Find the container serving the given base_url by matching its port."""
    try:
        # Extract port from base_url (e.g. https://localhost:35353 -> 35353)
        port = base_url.rstrip("/").rsplit(":", 1)[-1]
        result = subprocess.run(
            ["podman", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True,
        )
        for name in result.stdout.strip().split("\n"):
            if not name:
                continue
            port_result = subprocess.run(
                ["podman", "port", name, "8081/tcp"],
                capture_output=True, text=True,
            )
            if port in port_result.stdout:
                return name
    except Exception:
        pass
    return None


def steps(harness):
    # start_page: /card/blb/124 — auto-navigated by test runner.
    harness.wait_for_text("Artist's Talent")

    # Seed price data into the database via podman exec + python (sqlite3 CLI
    # is not installed in the container image).
    container = _find_container(harness.base_url)
    if container:
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
        subprocess.run(
            ["podman", "exec", container, "python", "-c", python_script],
            capture_output=True, text=True, check=True,
        )

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
