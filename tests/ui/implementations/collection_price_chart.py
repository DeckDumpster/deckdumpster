"""
Hand-written implementation for collection_price_chart.

Seeds price data via podman exec python3, opens the card modal for a card with
price data, and verifies the price chart appears. Then opens a card
with no price data and confirms the chart section is hidden.
"""

import subprocess


def _find_container(base_url):
    """Find the container serving the given base_url by matching its port."""
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
    # Seed price data into the database via podman exec python3.
    container = _find_container(harness.base_url)
    if container:
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
        subprocess.run(
            ["podman", "exec", container, "python3", "-c", seed_script],
            capture_output=True, text=True,
        )

    # start_page: /collection — auto-navigated by test runner.
    # Search for Artist's Talent (blb/124) which has seeded price data.
    harness.fill_by_placeholder("Search cards...", "Artist's Talent")
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

    # Now open a card with no price data to verify chart is hidden.
    # Still in grid view from above — search and click grid card.
    harness.fill_by_placeholder("Search cards...", "Orazca Puzzle-Door")
    harness.wait_for_visible(".sheet-card[data-idx]", timeout=15_000)
    harness.click_by_selector(".sheet-card[data-idx]")
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    # Scroll down — chart section should not be visible.
    harness.page.evaluate("document.querySelector('#modal-details').scrollTop = 9999")
    harness.page.wait_for_timeout(500)
    harness.assert_hidden(".price-chart-section.visible")
    harness.screenshot("final_state")
