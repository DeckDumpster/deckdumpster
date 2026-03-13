"""EDHREC per-commander card data fetcher and cache."""

import re
import sqlite3
from datetime import datetime, timedelta

import httpx


_CACHE_DAYS = 90
_EDHREC_URL = "https://json.edhrec.com/pages/commanders/{slug}.json"


class EdhrecCommander:
    """Fetch and cache per-commander card inclusion rates from EDHREC."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_inclusion_map(self, commander_name: str) -> dict[str, float]:
        """Return {card_name: inclusion_pct} for a commander.

        Fetches from EDHREC if cache is stale or missing.
        On network failure, returns stale cache or empty dict.
        """
        slug = self._slugify(commander_name)

        if not self._is_stale(commander_name):
            return self._load_cached(commander_name)

        try:
            cards = self._fetch(slug)
            self._store(commander_name, cards)
            return self._load_cached(commander_name)
        except (httpx.HTTPError, KeyError, ValueError):
            # Graceful degradation: stale cache or nothing
            cached = self._load_cached(commander_name)
            return cached

    def _slugify(self, name: str) -> str:
        """Convert commander name to EDHREC URL slug.

        "Atraxa, Praetors' Voice" -> "atraxa-praetors-voice"
        """
        s = name.lower()
        s = s.replace("'", "").replace(",", "")
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return s.strip("-")

    def _is_stale(self, commander_name: str) -> bool:
        """Check if cached data is older than _CACHE_DAYS."""
        row = self.conn.execute(
            "SELECT MIN(fetched_at) AS oldest FROM edhrec_commander_cards "
            "WHERE commander_name = ?",
            (commander_name,),
        ).fetchone()
        if not row or not row["oldest"]:
            return True
        try:
            fetched = datetime.fromisoformat(row["oldest"])
            return datetime.now() - fetched > timedelta(days=_CACHE_DAYS)
        except (ValueError, TypeError):
            return True

    def _fetch(self, slug: str) -> list[dict]:
        """Fetch card data from EDHREC JSON API."""
        url = _EDHREC_URL.format(slug=slug)
        resp = httpx.get(url, timeout=httpx.Timeout(30.0, connect=10.0))
        resp.raise_for_status()
        data = resp.json()

        cards = []
        for cardlist in data.get("cardlists", []):
            for card in cardlist.get("cardviews", []):
                name = card.get("name")
                inclusion = card.get("inclusion")
                num_decks = card.get("num_decks")
                if name and inclusion is not None and num_decks:
                    cards.append({
                        "name": name,
                        "inclusion": int(inclusion),
                        "num_decks": int(num_decks),
                        "synergy": card.get("synergy"),
                    })
        return cards

    def _store(self, commander_name: str, cards: list[dict]) -> None:
        """Upsert fetched cards into edhrec_commander_cards."""
        now = datetime.now().isoformat()
        for card in cards:
            self.conn.execute(
                "INSERT OR REPLACE INTO edhrec_commander_cards "
                "(commander_name, card_name, inclusion, num_decks, synergy, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    commander_name,
                    card["name"],
                    card["inclusion"],
                    card["num_decks"],
                    card.get("synergy"),
                    now,
                ),
            )
        self.conn.commit()

    def _load_cached(self, commander_name: str) -> dict[str, float]:
        """Load cached inclusion rates as {card_name: inclusion_pct}."""
        rows = self.conn.execute(
            "SELECT card_name, inclusion, num_decks FROM edhrec_commander_cards "
            "WHERE commander_name = ?",
            (commander_name,),
        ).fetchall()
        result = {}
        for r in rows:
            num_decks = r["num_decks"]
            if num_decks > 0:
                result[r["card_name"]] = r["inclusion"] / num_decks
        return result
