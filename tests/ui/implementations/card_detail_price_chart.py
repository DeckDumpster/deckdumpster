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

    # Seed price data into the database via podman exec.
    container = _find_container(harness.base_url)
    if container:
        sql = (
            "INSERT OR IGNORE INTO prices "
            "(set_code, collector_number, source, price_type, price, observed_at) "
            "VALUES "
            "('blb', '124', 'tcgplayer', 'normal', 8.50, date('now', '-60 days')),"
            "('blb', '124', 'tcgplayer', 'normal', 9.00, date('now', '-45 days')),"
            "('blb', '124', 'tcgplayer', 'normal', 10.00, date('now', '-30 days')),"
            "('blb', '124', 'tcgplayer', 'normal', 10.50, date('now', '-15 days')),"
            "('blb', '124', 'tcgplayer', 'normal', 10.46, date('now'));"
        )
        subprocess.run(
            ["podman", "exec", container, "sqlite3", "/data/collection.sqlite", sql],
            capture_output=True, text=True,
        )

    # Re-navigate so the chart picks up the seeded data.
    harness.navigate("/card/blb/124")
    harness.wait_for_text("Artist's Talent")

    # The price chart section should become visible.
    harness.wait_for_visible(".price-chart-section.visible", timeout=10_000)
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
