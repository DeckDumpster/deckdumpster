"""
UI test for single-card ingest button in the accordion sidebar.

Starts a local server with demo data, uses Playwright to:
1. Load the recent page and verify 3 cards in the grid
2. Click a card to open the accordion
3. Verify the "Add to Collection" button is visible
4. Click it and verify the card is removed from the grid
5. Verify only 2 cards remain and the ingested card's status changed in the DB

Requires: uv run shot-scraper install (one-time Playwright/Chromium setup)
To run: uv run pytest tests/test_single_card_ingest_ui.py -v
"""

import os
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

FIXTURE_DB = Path(__file__).parent / "fixtures" / "test-data.sqlite"


@pytest.fixture(scope="module")
def server():
    """Start a local server with demo data and yield (base_url, db_path)."""
    tmpdir = tempfile.mkdtemp(prefix="mtgc-ui-test-")
    db_path = os.path.join(tmpdir, "test.sqlite")
    mtgc_home = os.path.join(tmpdir, "mtgc_home")
    os.makedirs(os.path.join(mtgc_home, "ingest_images"), exist_ok=True)

    # Set up demo DB
    env = os.environ.copy()
    env["MTGC_DB"] = db_path
    env["MTGC_HOME"] = mtgc_home
    env["ANTHROPIC_API_KEY"] = "fake-key-for-testing"

    result = subprocess.run(
        ["uv", "run", "mtg", "setup", "--demo", "--from-fixture", str(FIXTURE_DB)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        pytest.fail(f"Demo setup failed:\n{result.stderr}")

    # Start server on a random-ish port
    port = 18899
    proc = subprocess.Popen(
        ["uv", "run", "mtg", "crack-pack-server", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for server to be ready
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("Server did not start in time")

    yield f"http://localhost:{port}", db_path

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def page():
    """Fresh Playwright browser page."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    p = context.new_page()
    yield p
    context.close()
    browser.close()
    pw.stop()


class TestSingleCardIngestUI:
    def test_accordion_shows_add_to_collection_button(self, server, page):
        """The 'Add to Collection' button appears for confirmed cards."""
        base_url, _ = server
        page.goto(f"{base_url}/recent")
        page.wait_for_selector(".img-card", timeout=5000)

        # Should have 3 cards
        cards = page.query_selector_all(".img-card")
        assert len(cards) == 3

        # Click the first card to open accordion
        cards[0].click()
        page.wait_for_selector(".acc-sidebar", timeout=3000)

        # The "Add to Collection" button should be visible
        btn = page.query_selector("button.primary")
        assert btn is not None
        assert btn.inner_text() == "Add to Collection"

    def test_single_card_ingest_removes_card_from_grid(self, server, page):
        """Clicking 'Add to Collection' ingests only that card and removes it."""
        base_url, db_path = server
        page.goto(f"{base_url}/recent")
        page.wait_for_selector(".img-card", timeout=5000)

        cards = page.query_selector_all(".img-card")
        assert len(cards) == 3

        # Get the image ID of the first card
        first_card_id = cards[0].get_attribute("data-id")

        # Click to open accordion
        cards[0].click()
        page.wait_for_selector(".acc-sidebar", timeout=3000)

        # Click "Add to Collection"
        btn = page.query_selector("button.primary")
        assert btn is not None
        btn.click()

        # Wait for the card to be removed from the grid
        page.wait_for_function(
            "document.querySelectorAll('#grid .img-card').length === 2",
            timeout=5000,
        )

        # Verify only 2 cards remain
        remaining = page.query_selector_all("#grid .img-card")
        assert len(remaining) == 2

        # The removed card's ID should not be in the grid
        remaining_ids = [c.get_attribute("data-id") for c in remaining]
        assert first_card_id not in remaining_ids

        # Verify the DB: the ingested image should be INGESTED
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM ingest_images WHERE id = ?", (int(first_card_id),)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["status"] == "INGESTED"

    def test_single_ingest_leaves_other_cards_unaffected(self, server, page):
        """After single-card ingest, remaining cards are still DONE in DB."""
        base_url, db_path = server
        page.goto(f"{base_url}/recent")
        page.wait_for_selector(".img-card", timeout=5000)

        cards = page.query_selector_all(".img-card")
        first_card_id = cards[0].get_attribute("data-id")

        # Get all card IDs before ingest
        all_ids = [c.get_attribute("data-id") for c in cards]
        other_ids = [cid for cid in all_ids if cid != first_card_id]

        # Click to open accordion and ingest
        cards[0].click()
        page.wait_for_selector(".acc-sidebar", timeout=3000)
        btn = page.query_selector("button.primary")
        btn.click()
        page.wait_for_function(
            "document.querySelectorAll('#grid .img-card').length === 2",
            timeout=5000,
        )

        # Other cards should still be DONE
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        for cid in other_ids:
            row = conn.execute(
                "SELECT status FROM ingest_images WHERE id = ?", (int(cid),)
            ).fetchone()
            assert row["status"] == "DONE", f"Card {cid} should still be DONE"
        conn.close()
