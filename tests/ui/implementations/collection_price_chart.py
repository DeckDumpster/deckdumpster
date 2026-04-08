"""
Hand-written implementation for collection_price_chart.

Seeds price data via podman exec, searches for the card, opens the modal,
verifies the chart appears, then opens a card with no prices and verifies
the chart is hidden.
"""

import subprocess


def _find_container(base_url):
    try:
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
    # Seed price data into the shared DB.
    container = _find_container(harness.base_url)
    if container:
        subprocess.run(
            ["podman", "exec", container, "python3", "-c",
             "import sqlite3, os; "
             "db = os.environ.get('MTGC_SHARED_DB', '/data/collection.sqlite'); "
             "c = sqlite3.connect(db); "
             "c.execute(\"INSERT OR IGNORE INTO prices (set_code,collector_number,source,price_type,price,observed_at) "
             "VALUES ('blb','124','tcgplayer','normal',10.46,'2026-04-01')\"); "
             "c.execute(\"INSERT OR REPLACE INTO latest_prices (set_code,collector_number,source,price_type,price,observed_at) "
             "VALUES ('blb','124','tcgplayer','normal',10.46,'2026-04-01')\"); "
             "c.commit(); c.close()"],
            capture_output=True, text=True, check=True,
        )

    # start_page: /collection — auto-navigated by test runner.
    harness.fill_by_placeholder("Search cards...", "Artist's Talent")
    harness.wait_for_visible("tr[data-idx]", timeout=500)
    harness.click_by_selector("#view-grid-btn")
    harness.click_by_selector(".sheet-card[data-idx]")
    harness.wait_for_visible("#card-modal-overlay.active", timeout=500)
    harness.page.evaluate("document.querySelector('#modal-details').scrollTop = 9999")
    # Chart.js render + async price fetch needs time.
    harness.wait_for_visible(".price-chart-section.visible", timeout=2000)
    harness.assert_visible("#price-chart-canvas")
    harness.screenshot("chart_visible")

    # Close the modal.
    harness.click_by_selector("#modal-close")
    harness.wait_for_hidden("#card-modal-overlay.active", timeout=500)

    # Open a card with no price data.
    # Switch to table view so we can wait for the card name text to appear.
    harness.click_by_selector("#view-table-btn")
    harness.fill_by_placeholder("Search cards...", "Orazca Puzzle-Door")
    harness.wait_for_text("Orazca", timeout=2000)
    # Switch back to grid and click.
    harness.click_by_selector("#view-grid-btn")
    harness.click_by_selector(".sheet-card[data-idx]")
    harness.wait_for_visible("#card-modal-overlay.active", timeout=500)
    harness.page.evaluate("document.querySelector('#modal-details').scrollTop = 9999")
    # Chart should NOT be visible for a card with no prices.
    harness.wait_for_hidden(".price-chart-section.visible", timeout=2000)
    harness.screenshot("final_state")
