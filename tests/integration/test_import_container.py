"""
Integration test: builds a container image, starts the server, and hits /api/import/resolve.

Moved from tests/test_import.py — this test spins up a Podman container,
which is too heavy for the unit test suite.

To run: uv run pytest tests/integration/test_import_container.py -v
Requires: podman
"""

import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
import requests
import urllib3

from mtg_collector.db.schema import init_db as schema_init_db


# ── Test data ────────────────────────────────────────────────────────

ORACLE_ALPHA = "aaaa-aaaa-aaaa-aaaa"
ORACLE_BETA = "bbbb-bbbb-bbbb-bbbb"

PRINTING_ALPHA_TST = "1111-1111-1111-1111"
PRINTING_BETA_TST = "2222-2222-2222-2222"


def _insert_test_data(conn):
    """Insert test cards, sets, and printings directly via SQL."""
    conn.execute(
        "INSERT INTO sets (set_code, set_name, set_type, released_at) VALUES (?, ?, ?, ?)",
        ("tst", "Test Set", "expansion", "2025-01-01"),
    )

    conn.execute(
        "INSERT INTO cards (oracle_id, name, type_line, mana_cost, cmc, colors, color_identity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ORACLE_ALPHA, "Test Card Alpha", "Creature", "{W}", 1.0, '["W"]', '["W"]'),
    )
    conn.execute(
        "INSERT INTO cards (oracle_id, name, type_line, mana_cost, cmc, colors, color_identity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ORACLE_BETA, "Test Card Beta", "Instant", "{U}", 1.0, '["U"]', '["U"]'),
    )

    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, "
        "frame_effects, border_color, full_art, promo, promo_types, finishes, artist, image_uri) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (PRINTING_ALPHA_TST, ORACLE_ALPHA, "tst", "001", "rare",
         "[]", "black", 0, 0, "[]", '["nonfoil","foil"]', "Artist A", None),
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, "
        "frame_effects, border_color, full_art, promo, promo_types, finishes, artist, image_uri) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (PRINTING_BETA_TST, ORACLE_BETA, "tst", "002", "common",
         "[]", "black", 0, 0, "[]", '["nonfoil"]', "Artist B", None),
    )

    conn.commit()


# ── Podman helpers ───────────────────────────────────────────────────

CONTAINER_NAME = "mtgc-test-import-resolve"
IMAGE_NAME = "mtgc:test-import"


def _podman_available():
    try:
        return subprocess.run(
            ["podman", "--version"], capture_output=True,
        ).returncode == 0
    except FileNotFoundError:
        return False


# ── Tests ────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _podman_available(), reason="podman not available")
class TestWebImportResolve:
    """Integration test: builds the container image, starts the server via
    the same entrypoint as production, and hits /api/import/resolve."""

    @pytest.fixture(scope="class")
    def container_url(self, tmp_path_factory):
        """Build image, seed DB, start container, yield base URL."""
        repo_dir = Path(__file__).resolve().parent.parent.parent

        # 1. Create and seed a temp DB on the host
        db_dir = tmp_path_factory.mktemp("import-test-db")
        db_path = db_dir / "collection.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        schema_init_db(conn)
        _insert_test_data(conn)
        conn.close()

        # 2. Build the container image from the same Containerfile as prod
        subprocess.run(
            ["podman", "build", "-t", IMAGE_NAME, "-f", "Containerfile", "."],
            cwd=str(repo_dir), check=True,
            capture_output=True,
        )

        # 3. Clean up any stale container from a previous run
        subprocess.run(
            ["podman", "rm", "-f", CONTAINER_NAME],
            capture_output=True,
        )

        # 4. Start container — same entrypoint as production, seeded DB mounted in
        subprocess.run(
            [
                "podman", "run", "-d",
                "--name", CONTAINER_NAME,
                "-p", ":8081",
                "-e", "ANTHROPIC_API_KEY=test-dummy",
                "-v", f"{db_path}:/data/collection.sqlite:Z",
                IMAGE_NAME,
            ],
            check=True, capture_output=True,
        )

        # 5. Discover the auto-assigned host port
        port_output = subprocess.check_output(
            ["podman", "port", CONTAINER_NAME, "8081/tcp"], text=True,
        ).strip()
        port = port_output.split(":")[-1]

        # 6. Wait for the server to accept connections
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        base_url = f"https://127.0.0.1:{port}"
        for attempt in range(30):
            try:
                requests.get(f"{base_url}/", verify=False, timeout=2)
                break
            except Exception:
                time.sleep(1)
        else:
            logs = subprocess.check_output(
                ["podman", "logs", CONTAINER_NAME], text=True,
                stderr=subprocess.STDOUT,
            )
            subprocess.run(["podman", "rm", "-f", CONTAINER_NAME], capture_output=True)
            pytest.fail(f"Container failed to start within 30s.\nLogs:\n{logs}")

        yield base_url

        subprocess.run(["podman", "rm", "-f", CONTAINER_NAME], capture_output=True)

    def test_resolve_via_web_api(self, container_url):
        """/api/import/resolve resolves cards using local DB, not Scryfall."""
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.post(
            f"{container_url}/api/import/resolve",
            json={
                "format": "moxfield",
                "rows": [
                    {"name": "Test Card Alpha", "set_code": "tst",
                     "collector_number": "001", "quantity": 1, "raw": {}},
                    {"name": "Test Card Beta", "set_code": "tst",
                     "collector_number": "002", "quantity": 1, "raw": {}},
                ],
            },
            verify=False,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["resolved"] == 2
        assert data["summary"]["failed"] == 0
        assert data["resolved"][0]["printing_id"] == PRINTING_ALPHA_TST
        assert data["resolved"][1]["printing_id"] == PRINTING_BETA_TST

    def test_resolve_wrong_set_cn_via_web_api(self, container_url):
        """Web UI Doctor Doom test: wrong set/cn falls back to name."""
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.post(
            f"{container_url}/api/import/resolve",
            json={
                "format": "moxfield",
                "rows": [
                    {"name": "Test Card Alpha", "set_code": "tst",
                     "collector_number": "002", "quantity": 1, "raw": {}},
                ],
            },
            verify=False,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["resolved"] == 1
        # Must resolve to Alpha, not Beta (whose set/cn was provided)
        assert data["resolved"][0]["printing_id"] == PRINTING_ALPHA_TST
