"""
Integration test: hits /api/import/resolve on the running test container.

Tests that import resolution works end-to-end through the web API using
the pre-seeded demo data in the test container.

To run: uv run pytest tests/integration/test_import_container.py -v --instance <instance>
"""


class TestWebImportResolve:
    """Hit /api/import/resolve on the running test container."""

    def test_resolve_via_web_api(self, api):
        """/api/import/resolve resolves cards using local DB, not Scryfall."""
        status, data = api.post(
            "/api/import/resolve",
            {
                "format": "moxfield",
                "rows": [
                    {"name": "Abrade", "set_code": "fdn",
                     "collector_number": "188", "quantity": 1, "raw": {}},
                ],
            },
        )
        assert status == 200
        assert data["summary"]["resolved"] >= 1
        assert data["resolved"][0]["resolved"] is True

    def test_resolve_unknown_card(self, api):
        """Unknown card name returns failed resolution, not a crash."""
        status, data = api.post(
            "/api/import/resolve",
            {
                "format": "moxfield",
                "rows": [
                    {"name": "Nonexistent Card ZZZZZ", "set_code": "zzz",
                     "collector_number": "999", "quantity": 1, "raw": {}},
                ],
            },
        )
        assert status == 200
        assert data["summary"]["failed"] == 1
        assert data["resolved"][0]["resolved"] is False
