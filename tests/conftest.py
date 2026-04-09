"""Top-level conftest for search test infrastructure."""

import shutil
import sqlite3
import tempfile

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--scryfall",
        action="store_true",
        default=False,
        help="Enable Scryfall API tests (requires network)",
    )
    parser.addoption(
        "--seeds",
        action="store",
        default="200",
        help="Number of generative test seeds (default: 200)",
    )
    parser.addoption(
        "--seed",
        action="store",
        default=None,
        help="Run a single generative seed (for reproduction)",
    )
    parser.addoption(
        "--search-db",
        action="store",
        default=None,
        help="Path to DB for search tests (default: test fixture, or ~/.mtgc/collection.sqlite with --scryfall)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--scryfall"):
        skip = pytest.mark.skip(reason="need --scryfall option to run")
        for item in items:
            if "scryfall" in item.keywords:
                item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "scryfall: tests requiring Scryfall API access")
    config.addinivalue_line("markers", "generative: seed-based generative tests")


def _resolve_search_db_path(request) -> str:
    """Resolve which DB to use for search tests.

    Priority:
    1. --search-db explicit path
    2. ~/.mtgc/collection.sqlite (if --scryfall and it exists — Scryfall
       comparison only makes sense against the full DB)
    3. tests/fixtures/test-data.sqlite (default for offline tests)
    """
    import pathlib

    explicit = request.config.getoption("--search-db")
    if explicit:
        path = pathlib.Path(explicit)
        if not path.exists():
            pytest.skip(f"--search-db path not found: {explicit}")
        return str(path)

    if request.config.getoption("--scryfall"):
        full_db = pathlib.Path.home() / ".mtgc" / "collection.sqlite"
        if full_db.exists():
            return str(full_db)

    fixture = pathlib.Path(__file__).parent / "fixtures" / "test-data.sqlite"
    if not fixture.exists():
        pytest.skip("test-data.sqlite fixture not found")
    return str(fixture)


@pytest.fixture(scope="session")
def search_db(request):
    """Session-scoped migrated copy of the search DB.

    With --scryfall: uses ~/.mtgc/collection.sqlite (full Scryfall corpus)
    if available, since comparison only makes sense against the complete DB.
    Without --scryfall: uses the 16-set test fixture for fast offline tests.
    Explicit --search-db overrides both.
    """
    import pathlib

    from mtg_collector.db.schema import init_db

    source = _resolve_search_db_path(request)

    # Copy to temp so we can migrate without touching the original
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    shutil.copy2(source, tmp.name)

    conn = sqlite3.connect(tmp.name)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    yield conn

    conn.close()
    pathlib.Path(tmp.name).unlink(missing_ok=True)


@pytest.fixture(scope="session")
def known_printing_ids(search_db):
    """All non-digital printing_ids in the search DB."""
    rows = search_db.execute(
        "SELECT printing_id FROM printings WHERE digital = 0"
    ).fetchall()
    return frozenset(row["printing_id"] for row in rows)


@pytest.fixture(scope="session")
def known_oracle_ids(search_db):
    """All oracle_ids that have at least one non-digital printing in the search DB.

    Used for Scryfall comparison — we deduplicate by oracle_id to match
    Scryfall's default unique:cards behavior.
    """
    rows = search_db.execute(
        "SELECT DISTINCT oracle_id FROM printings WHERE digital = 0"
    ).fetchall()
    return frozenset(row["oracle_id"] for row in rows)


@pytest.fixture(scope="session")
def scryfall_cache(request):
    """SQLite cache for Scryfall API responses. Only created when --scryfall is used.

    Cached responses persist across runs — only uncached queries hit the API.
    """
    import pathlib

    from tests.search_helpers.scryfall_client import init_cache

    cache_path = pathlib.Path(__file__).parent / ".scryfall_cache.sqlite"
    conn = init_cache(cache_path)

    yield conn

    conn.close()


@pytest.fixture
def seed_range(request):
    """Range of seeds for generative tests."""
    single = request.config.getoption("--seed")
    if single is not None:
        return range(int(single), int(single) + 1)
    count = int(request.config.getoption("--seeds"))
    return range(count)
