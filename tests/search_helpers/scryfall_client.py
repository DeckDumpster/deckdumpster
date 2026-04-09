"""Rate-limited Scryfall search client with SQLite response caching.

Cache is keyed by query string. Cached responses persist across generator
changes — a query's Scryfall result doesn't depend on how it was generated.
Only uncached queries trigger network requests.
"""

import hashlib
import json
import pathlib
import sqlite3
import time
import urllib.parse

import requests

_BASE_URL = "https://api.scryfall.com/cards/search"
_USER_AGENT = "MTGCollectionTool/2.0 SearchTests"
_MIN_INTERVAL = 0.1  # 100ms between requests
_MAX_PAGES = 3  # up to 525 cards

_last_request_time = 0.0


def _rate_limit():
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()


def init_cache(cache_path: str | pathlib.Path) -> sqlite3.Connection:
    """Open or create the Scryfall cache DB."""
    conn = sqlite3.connect(str(cache_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_cache (
            query_hash TEXT PRIMARY KEY,
            query_text TEXT NOT NULL,
            response_json TEXT NOT NULL,
            total_cards INTEGER,
            status_code INTEGER NOT NULL DEFAULT 200,
            fetched_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def scryfall_search(cache_conn: sqlite3.Connection, query: str) -> dict:
    """Search Scryfall with caching.

    Returns {"status_code": int, "cards": list[dict], "total_cards": int}.
    """
    key = _cache_key(query)

    # Check cache
    row = cache_conn.execute(
        "SELECT response_json, status_code, total_cards FROM query_cache WHERE query_hash = ?",
        (key,),
    ).fetchone()
    if row:
        return {
            "status_code": row["status_code"],
            "cards": json.loads(row["response_json"]),
            "total_cards": row["total_cards"] or 0,
        }

    # Fetch from Scryfall
    cards = []
    total_cards = 0
    url = f"{_BASE_URL}?{urllib.parse.urlencode({'q': query})}"

    _rate_limit()
    first_resp = _request_with_retry(url)
    status_code = first_resp.status_code

    if status_code == 200:
        data = first_resp.json()
        total_cards = data.get("total_cards", 0)
        cards.extend(data.get("data", []))

        # Paginate
        for _page in range(_MAX_PAGES - 1):
            if not data.get("has_more"):
                break
            url = data.get("next_page")
            if not url:
                break
            _rate_limit()
            resp = _request_with_retry(url)
            if resp.status_code != 200:
                break
            data = resp.json()
            cards.extend(data.get("data", []))

    # Cache result
    from mtg_collector.utils import now_iso

    cache_conn.execute(
        """INSERT OR REPLACE INTO query_cache
           (query_hash, query_text, response_json, total_cards, status_code, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (key, query, json.dumps(cards), total_cards, status_code, now_iso()),
    )
    cache_conn.commit()

    return {"status_code": status_code, "cards": cards, "total_cards": total_cards}


def _request_with_retry(url: str, max_retries: int = 3) -> requests.Response:
    """HTTP GET with exponential backoff on 429."""
    session = requests.Session()
    session.headers["User-Agent"] = _USER_AGENT

    for attempt in range(max_retries + 1):
        resp = session.get(url)
        if resp.status_code == 429:
            wait = 0.5 * (2**attempt)
            time.sleep(wait)
            continue
        return resp
    return resp
