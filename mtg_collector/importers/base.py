"""Base importer interface."""

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from mtg_collector.db.models import CollectionEntry


@dataclass
class ImportResult:
    """Result of an import operation."""

    total_rows: int = 0
    cards_added: int = 0
    cards_skipped: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class BaseImporter(ABC):
    """Abstract base class for collection importers."""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Human-readable format name."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Source identifier for imported cards."""
        pass

    @abstractmethod
    def parse_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Parse the import file and return raw row data.

        Args:
            file_path: Path to import file

        Returns:
            List of dicts, one per row
        """
        pass

    @abstractmethod
    def row_to_lookup(self, row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], int]:
        """
        Convert a row to card lookup parameters.

        Args:
            row: Parsed row dict

        Returns:
            Tuple of (card_name, set_code, collector_number, quantity)
        """
        pass

    @abstractmethod
    def row_to_entry(self, row: Dict[str, Any], printing_id: str) -> CollectionEntry:
        """
        Convert a row to a CollectionEntry.

        Args:
            row: Parsed row dict
            printing_id: Resolved printing ID

        Returns:
            CollectionEntry ready to insert
        """
        pass

    def import_file(
        self,
        file_path: str,
        conn: sqlite3.Connection,
        card_repo,
        set_repo,
        printing_repo,
        collection_repo,
        dry_run: bool = False,
    ) -> ImportResult:
        """
        Import a file into the collection.

        Args:
            file_path: Path to import file
            conn: Database connection
            card_repo, set_repo, printing_repo, collection_repo: Repositories
            dry_run: If True, don't actually insert

        Returns:
            ImportResult with statistics
        """
        result = ImportResult()

        rows = self.parse_file(file_path)
        result.total_rows = len(rows)

        for row in rows:
            try:
                name, set_code, collector_number, quantity = self.row_to_lookup(row)

                if not name:
                    result.cards_skipped += 1
                    continue

                printing_id = self._resolve_card(
                    card_repo, printing_repo, name, set_code, collector_number,
                )

                if not printing_id:
                    result.errors.append(f"Could not find: {name} ({set_code or 'any set'})")
                    result.cards_skipped += 1
                    continue

                if not dry_run:
                    for _ in range(quantity):
                        entry = self.row_to_entry(row, printing_id)
                        collection_repo.add(entry)

                result.cards_added += quantity

            except Exception as e:
                result.errors.append(f"Error processing row: {e}")
                result.cards_skipped += 1

        if not dry_run:
            conn.commit()

        return result

    def _resolve_card(
        self,
        card_repo,
        printing_repo,
        name: str,
        set_code: Optional[str],
        collector_number: Optional[str],
    ) -> Optional[str]:
        """Resolve a card using the local database. Returns printing_id or None."""
        # Normalize DFC names: Moxfield exports "Front / Back", Scryfall stores "Front // Back"
        if " / " in name:
            name = name.replace(" / ", " // ")

        # Strategy 1: If set_code + collector_number, look up printing and validate name
        if set_code and collector_number:
            printing = printing_repo.get_by_set_cn(set_code, collector_number)
            if printing:
                card = card_repo.get(printing.oracle_id)
                if card and self._name_matches(name, card.name):
                    return printing.printing_id
                # Check flavor_name for UB/crossover cards (e.g. TMNT set
                # renames Vigor → Heralds of the Shredder)
                if printing.raw_json:
                    raw = json.loads(printing.raw_json)
                    flavor = raw.get("flavor_name")
                    if flavor and self._name_matches(name, flavor):
                        return printing.printing_id
                # Name mismatch — fall through to name-based lookup

        # Strategy 2: Name-based lookup
        card = card_repo.get_by_name(name) or card_repo.search_by_name(name)
        if card:
            printings = printing_repo.get_by_oracle_id(card.oracle_id)
            if printings:
                if set_code:
                    for p in printings:
                        if p.set_code.lower() == set_code.lower():
                            return p.printing_id
                return printings[0].printing_id

        # Strategy 3: Flavor name lookup (UB/crossover cards with alternate names)
        printing = printing_repo.get_by_flavor_name(name, set_code)
        if printing:
            return printing.printing_id

        return None

    @staticmethod
    def _name_matches(search_name: str, db_name: str) -> bool:
        """Check if search_name matches db_name (case-insensitive, DFC-aware)."""
        search_lower = search_name.lower()
        db_lower = db_name.lower()

        if search_lower == db_lower:
            return True

        # DFC: db stores "Front // Back", search might be just "Front"
        if " // " in db_lower:
            front_face = db_lower.split(" // ")[0]
            if search_lower == front_face:
                return True

        return False
