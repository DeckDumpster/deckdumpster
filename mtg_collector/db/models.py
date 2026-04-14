"""Database models and repositories."""

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mtg_collector.utils import now_iso, parse_json_array, to_json_array


@dataclass
class Card:
    """Abstract card (oracle-level)."""
    oracle_id: str
    name: str
    type_line: Optional[str] = None
    mana_cost: Optional[str] = None
    cmc: Optional[float] = None
    oracle_text: Optional[str] = None
    colors: List[str] = field(default_factory=list)
    color_identity: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    legalities: Optional[Dict] = None


@dataclass
class Set:
    """MTG set information."""
    set_code: str
    set_name: str
    set_type: Optional[str] = None
    released_at: Optional[str] = None
    digital: int = 0  # 1 if MTGO/Arena-only set
    cards_fetched_at: Optional[str] = None  # When full card list was cached


@dataclass
class Printing:
    """Specific card printing."""
    printing_id: str
    oracle_id: str
    set_code: str
    collector_number: str
    rarity: Optional[str] = None
    frame_effects: List[str] = field(default_factory=list)
    border_color: Optional[str] = None
    full_art: bool = False
    promo: bool = False
    promo_types: List[str] = field(default_factory=list)
    finishes: List[str] = field(default_factory=list)
    artist: Optional[str] = None
    image_uri: Optional[str] = None
    raw_json: Optional[str] = None  # Full card data as JSON string (cached from bulk import)
    power: Optional[str] = None
    toughness: Optional[str] = None
    loyalty: Optional[str] = None
    layout: Optional[str] = None
    flavor_text: Optional[str] = None
    flavor_name: Optional[str] = None
    watermark: Optional[str] = None
    digital: bool = False
    reserved: bool = False
    reprint: bool = False
    produced_mana: List[str] = field(default_factory=list)
    games: List[str] = field(default_factory=list)

    def get_card_data(self) -> Optional[Dict]:
        """Parse and return the full card data as a dict."""
        if self.raw_json:
            import json
            return json.loads(self.raw_json)
        return None


@dataclass
class Order:
    """An order from a card vendor."""
    id: Optional[int]
    order_number: Optional[str] = None
    source: Optional[str] = None  # 'tcgplayer', 'cardkingdom', 'other'
    seller_name: Optional[str] = None
    order_date: Optional[str] = None
    subtotal: Optional[float] = None
    shipping: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    shipping_status: Optional[str] = None
    estimated_delivery: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class CollectionEntry:
    """A physical card in the user's collection."""
    id: Optional[int]
    printing_id: str
    finish: str
    condition: str = "Near Mint"
    language: str = "English"
    purchase_price: Optional[float] = None
    acquired_at: Optional[str] = None
    source: str = "manual"
    source_image: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    tradelist: bool = False
    alter: bool = False
    proxy: bool = False
    signed: bool = False
    misprint: bool = False
    status: str = "owned"
    sale_price: Optional[float] = None
    order_id: Optional[int] = None
    binder_id: Optional[int] = None
    batch_id: Optional[int] = None


DECK_STATE_IDEA = 1
DECK_STATE_READY = 2
DECK_STATE_CONSTRUCTED = 3

STATE_NAME_TO_ID = {"idea": DECK_STATE_IDEA, "ready": DECK_STATE_READY, "constructed": DECK_STATE_CONSTRUCTED}


@dataclass
class Deck:
    """A deck grouping — idea, ready, or constructed."""
    id: Optional[int]
    name: str
    description: Optional[str] = None
    format: Optional[str] = None
    is_precon: bool = False
    sleeve_color: Optional[str] = None
    deck_box: Optional[str] = None
    storage_location: Optional[str] = None
    origin_set_code: Optional[str] = None
    origin_theme: Optional[str] = None
    origin_variation: Optional[int] = None
    state_id: int = DECK_STATE_IDEA
    commander_oracle_id: Optional[str] = None
    commander_printing_id: Optional[str] = None
    plan: Optional[str] = None
    sub_plans: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Binder:
    """A physical binder grouping."""
    id: Optional[int]
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    binder_type: Optional[str] = None
    storage_location: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class CollectionView:
    """A saved collection filter view."""
    id: Optional[int]
    name: str
    description: Optional[str] = None
    filters_json: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Batch:
    """A batch grouping cards from any ingestion flow."""
    id: Optional[int]
    batch_uuid: str
    name: Optional[str] = None
    deck_id: Optional[int] = None
    deck_zone: Optional[str] = None
    card_count: int = 0
    batch_type: str = "corner"
    product_type: Optional[str] = None
    set_code: Optional[str] = None
    notes: Optional[str] = None
    order_id: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


# Backward-compatible alias
CornerBatch = Batch


@dataclass
class SealedProduct:
    """A sealed MTG product (booster box, bundle, deck, etc.)."""
    uuid: str
    name: str
    set_code: str
    category: str
    subtype: Optional[str] = None
    tcgplayer_product_id: Optional[str] = None
    card_count: Optional[int] = None
    product_size: Optional[int] = None
    release_date: Optional[str] = None
    purchase_url_tcgplayer: Optional[str] = None
    purchase_url_cardkingdom: Optional[str] = None
    contents_json: Optional[str] = None
    imported_at: Optional[str] = None
    source: str = "mtgjson"


@dataclass
class SealedCollectionEntry:
    """A sealed product in the user's collection."""
    id: Optional[int]
    sealed_product_uuid: str
    quantity: int = 1
    condition: str = "Near Mint"
    purchase_price: Optional[float] = None
    purchase_date: Optional[str] = None
    source: Optional[str] = None
    seller_name: Optional[str] = None
    notes: Optional[str] = None
    status: str = "owned"
    sale_price: Optional[float] = None
    added_at: Optional[str] = None


@dataclass
class WishlistEntry:
    """A card the user wants to acquire."""
    id: Optional[int]
    oracle_id: str
    printing_id: Optional[str] = None
    max_price: Optional[float] = None
    priority: int = 0
    notes: Optional[str] = None
    added_at: Optional[str] = None
    source: str = "manual"
    fulfilled_at: Optional[str] = None


class CardRepository:
    """CRUD operations for cards table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, card: Card) -> None:
        """Insert or update a card."""
        legalities_json = None
        if card.legalities is not None:
            legalities_json = json.dumps(card.legalities) if isinstance(card.legalities, dict) else card.legalities
        self.conn.execute(
            """
            INSERT INTO cards
            (oracle_id, name, type_line, mana_cost, cmc, oracle_text, colors, color_identity,
             keywords, legalities)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(oracle_id) DO UPDATE SET
                name = excluded.name,
                type_line = excluded.type_line,
                mana_cost = excluded.mana_cost,
                cmc = excluded.cmc,
                oracle_text = excluded.oracle_text,
                colors = excluded.colors,
                color_identity = excluded.color_identity,
                keywords = excluded.keywords,
                legalities = excluded.legalities
            """,
            (
                card.oracle_id,
                card.name,
                card.type_line,
                card.mana_cost,
                card.cmc,
                card.oracle_text,
                to_json_array(card.colors),
                to_json_array(card.color_identity),
                to_json_array(card.keywords),
                legalities_json,
            ),
        )

    def _row_to_card(self, row) -> Card:
        """Convert a database row to a Card object."""
        legalities = None
        leg_raw = row["legalities"] if "legalities" in row.keys() else None
        if leg_raw:
            legalities = json.loads(leg_raw) if isinstance(leg_raw, str) else leg_raw
        return Card(
            oracle_id=row["oracle_id"],
            name=row["name"],
            type_line=row["type_line"],
            mana_cost=row["mana_cost"],
            cmc=row["cmc"],
            oracle_text=row["oracle_text"],
            colors=parse_json_array(row["colors"]),
            color_identity=parse_json_array(row["color_identity"]),
            keywords=parse_json_array(row["keywords"] if "keywords" in row.keys() else None),
            legalities=legalities,
        )

    def get(self, oracle_id: str) -> Optional[Card]:
        """Get a card by oracle_id."""
        cursor = self.conn.execute(
            "SELECT * FROM cards WHERE oracle_id = ?", (oracle_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_card(row)

    def get_by_name(self, name: str) -> Optional[Card]:
        """Get a card by exact name."""
        cursor = self.conn.execute(
            "SELECT * FROM cards WHERE name = ?", (name,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_card(row)

    def search_by_name(self, name: str) -> Optional[Card]:
        """Search for a card by name (case-insensitive, handles DFCs).

        Handles double-faced cards where the DB stores "Front // Back"
        but the search term is just "Front".
        """
        # Try case-insensitive exact match first
        cursor = self.conn.execute(
            "SELECT * FROM cards WHERE name COLLATE NOCASE = ?", (name,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_card(row)

        # Try matching front face of double-faced cards ("Name // ...")
        cursor = self.conn.execute(
            "SELECT * FROM cards WHERE name LIKE ? LIMIT 1",
            (name + " // %",),
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_card(row)

        return None

    def search_cards_by_name(self, name: str, limit: int = 20) -> List[Card]:
        """Search for cards by name, returning multiple results.

        Case-insensitive exact match first, then DFC front-face match,
        then partial LIKE match.
        """
        results = []
        seen = set()

        # Exact case-insensitive match
        for row in self.conn.execute(
            "SELECT * FROM cards WHERE name COLLATE NOCASE = ?", (name,)
        ):
            results.append(self._row_to_card(row))
            seen.add(row["oracle_id"])

        # DFC front-face match
        if seen:
            placeholders = ",".join("?" * len(seen))
            query = f"SELECT * FROM cards WHERE name LIKE ? COLLATE NOCASE AND oracle_id NOT IN ({placeholders})"
            params = (name + " // %", *seen)
        else:
            query = "SELECT * FROM cards WHERE name LIKE ? COLLATE NOCASE"
            params = (name + " // %",)
        for row in self.conn.execute(query, params):
            results.append(self._row_to_card(row))
            seen.add(row["oracle_id"])

        if len(results) >= limit:
            return results[:limit]

        # Partial match (substring)
        exclude = f"AND oracle_id NOT IN ({','.join('?' * len(seen))})" if seen else ""
        for row in self.conn.execute(
            f"SELECT * FROM cards WHERE name LIKE ? COLLATE NOCASE {exclude} LIMIT ?",
            (f"%{name}%", *seen, limit - len(results)),
        ):
            results.append(self._row_to_card(row))

        return results


class SetRepository:
    """CRUD operations for sets table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, s: Set) -> None:
        """Insert or update a set."""
        self.conn.execute(
            """
            INSERT INTO sets (set_code, set_name, set_type, released_at, digital, cards_fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(set_code) DO UPDATE SET
                set_name = excluded.set_name,
                set_type = excluded.set_type,
                released_at = excluded.released_at,
                digital = excluded.digital,
                cards_fetched_at = COALESCE(excluded.cards_fetched_at, sets.cards_fetched_at)
            """,
            (s.set_code, s.set_name, s.set_type, s.released_at, s.digital, s.cards_fetched_at),
        )

    def get(self, set_code: str) -> Optional[Set]:
        """Get a set by code."""
        cursor = self.conn.execute(
            "SELECT * FROM sets WHERE set_code = ?", (set_code,)
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return Set(
            set_code=row["set_code"],
            set_name=row["set_name"],
            set_type=row["set_type"],
            released_at=row["released_at"],
            digital=row["digital"] if "digital" in row.keys() else 0,
            cards_fetched_at=row["cards_fetched_at"],
        )

    def get_by_name(self, name: str) -> Optional[Set]:
        """Find a set by name (case-insensitive, with partial match fallback)."""
        name_lower = name.lower()

        # Try exact case-insensitive match
        cursor = self.conn.execute(
            "SELECT * FROM sets WHERE set_name COLLATE NOCASE = ?", (name,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_set(row)

        # Try partial match (set name contains the search term)
        cursor = self.conn.execute(
            "SELECT * FROM sets WHERE LOWER(set_name) LIKE ? LIMIT 1",
            (f"%{name_lower}%",),
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_set(row)

        return None

    def _row_to_set(self, row) -> Set:
        return Set(
            set_code=row["set_code"],
            set_name=row["set_name"],
            set_type=row["set_type"],
            released_at=row["released_at"],
            digital=row["digital"] if "digital" in row.keys() else 0,
            cards_fetched_at=row["cards_fetched_at"],
        )

    def exists(self, set_code: str) -> bool:
        """Check if a set exists."""
        cursor = self.conn.execute(
            "SELECT 1 FROM sets WHERE set_code = ?", (set_code,)
        )
        return cursor.fetchone() is not None

    def is_cards_cached(self, set_code: str) -> bool:
        """Check if a set's card list has been fully cached."""
        cursor = self.conn.execute(
            "SELECT cards_fetched_at FROM sets WHERE set_code = ?", (set_code,)
        )
        row = cursor.fetchone()
        return row is not None and row["cards_fetched_at"] is not None

    def mark_cards_cached(self, set_code: str) -> None:
        """Mark a set's card list as fully cached."""
        from mtg_collector.utils import now_iso
        self.conn.execute(
            "UPDATE sets SET cards_fetched_at = ? WHERE set_code = ?",
            (now_iso(), set_code),
        )

    def normalize_code(self, raw: str) -> Optional[str]:
        """Normalize a set code or name to a valid set code using the local DB.

        Tries exact code match, then case-insensitive code, then name match.
        Returns lowercase set code, or None if not found.
        """
        raw = raw.strip()
        raw_lower = raw.lower()

        # Exact code match
        s = self.get(raw_lower)
        if s:
            return s.set_code

        # Case-insensitive code match (try as-is in case DB has different casing)
        cursor = self.conn.execute(
            "SELECT set_code FROM sets WHERE set_code COLLATE NOCASE = ? LIMIT 1",
            (raw,),
        )
        row = cursor.fetchone()
        if row:
            return row["set_code"]

        # Name match (exact then partial)
        s = self.get_by_name(raw)
        if s:
            return s.set_code

        return None


class PrintingRepository:
    """CRUD operations for printings table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, p: Printing) -> None:
        """Insert or update a printing."""
        self.conn.execute(
            """
            INSERT INTO printings
            (printing_id, oracle_id, set_code, collector_number, rarity,
             frame_effects, border_color, full_art, promo, promo_types,
             finishes, artist, image_uri, raw_json,
             power, toughness, loyalty, layout, flavor_text, flavor_name,
             watermark, digital, reserved, reprint, produced_mana, games)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(printing_id) DO UPDATE SET
                oracle_id = excluded.oracle_id,
                set_code = excluded.set_code,
                collector_number = excluded.collector_number,
                rarity = excluded.rarity,
                frame_effects = excluded.frame_effects,
                border_color = excluded.border_color,
                full_art = excluded.full_art,
                promo = excluded.promo,
                promo_types = excluded.promo_types,
                finishes = excluded.finishes,
                artist = excluded.artist,
                image_uri = excluded.image_uri,
                raw_json = excluded.raw_json,
                power = excluded.power,
                toughness = excluded.toughness,
                loyalty = excluded.loyalty,
                layout = excluded.layout,
                flavor_text = excluded.flavor_text,
                flavor_name = excluded.flavor_name,
                watermark = excluded.watermark,
                digital = excluded.digital,
                reserved = excluded.reserved,
                reprint = excluded.reprint,
                produced_mana = excluded.produced_mana,
                games = excluded.games
            """,
            (
                p.printing_id,
                p.oracle_id,
                p.set_code,
                p.collector_number,
                p.rarity,
                to_json_array(p.frame_effects),
                p.border_color,
                1 if p.full_art else 0,
                1 if p.promo else 0,
                to_json_array(p.promo_types),
                to_json_array(p.finishes),
                p.artist,
                p.image_uri,
                p.raw_json,
                p.power,
                p.toughness,
                p.loyalty,
                p.layout,
                p.flavor_text,
                p.flavor_name,
                p.watermark,
                1 if p.digital else 0,
                1 if p.reserved else 0,
                1 if p.reprint else 0,
                to_json_array(p.produced_mana),
                to_json_array(p.games),
            ),
        )

    def get(self, printing_id: str) -> Optional[Printing]:
        """Get a printing by printing_id."""
        cursor = self.conn.execute(
            "SELECT * FROM printings WHERE printing_id = ?", (printing_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_printing(row)

    def get_by_set_cn(self, set_code: str, collector_number: str) -> Optional[Printing]:
        """Get a printing by set code and collector number."""
        cursor = self.conn.execute(
            "SELECT * FROM printings WHERE set_code = ? AND collector_number = ?",
            (set_code, collector_number),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_printing(row)

    def get_by_oracle_id(self, oracle_id: str) -> List[Printing]:
        """Get all printings for a card."""
        cursor = self.conn.execute(
            "SELECT * FROM printings WHERE oracle_id = ? ORDER BY set_code, collector_number",
            (oracle_id,),
        )
        return [self._row_to_printing(row) for row in cursor]

    def get_by_flavor_name(self, name: str, set_code: Optional[str] = None) -> Optional[Printing]:
        """Find a printing by flavor_name (UB/crossover cards with alternate names)."""
        if set_code:
            cursor = self.conn.execute(
                "SELECT * FROM printings"
                " WHERE set_code = ? AND json_extract(raw_json, '$.flavor_name') = ? COLLATE NOCASE",
                (set_code, name),
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM printings"
                " WHERE json_extract(raw_json, '$.flavor_name') = ? COLLATE NOCASE"
                " LIMIT 1",
                (name,),
            )
        row = cursor.fetchone()
        return self._row_to_printing(row) if row else None

    def exists(self, printing_id: str) -> bool:
        """Check if a printing exists."""
        cursor = self.conn.execute(
            "SELECT 1 FROM printings WHERE printing_id = ?", (printing_id,)
        )
        return cursor.fetchone() is not None

    def _row_to_printing(self, row: sqlite3.Row) -> Printing:
        keys = row.keys()

        def _get(key, default=None):
            return row[key] if key in keys else default

        return Printing(
            printing_id=row["printing_id"],
            oracle_id=row["oracle_id"],
            set_code=row["set_code"],
            collector_number=row["collector_number"],
            rarity=row["rarity"],
            frame_effects=parse_json_array(row["frame_effects"]),
            border_color=row["border_color"],
            full_art=bool(row["full_art"]),
            promo=bool(row["promo"]),
            promo_types=parse_json_array(row["promo_types"]),
            finishes=parse_json_array(row["finishes"]),
            artist=row["artist"],
            image_uri=row["image_uri"],
            raw_json=_get("raw_json"),
            power=_get("power"),
            toughness=_get("toughness"),
            loyalty=_get("loyalty"),
            layout=_get("layout"),
            flavor_text=_get("flavor_text"),
            flavor_name=_get("flavor_name"),
            watermark=_get("watermark"),
            digital=bool(_get("digital", 0)),
            reserved=bool(_get("reserved", 0)),
            reprint=bool(_get("reprint", 0)),
            produced_mana=parse_json_array(_get("produced_mana")),
            games=parse_json_array(_get("games")),
        )


class CollectionRepository:
    """CRUD operations for collection table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, entry: CollectionEntry) -> int:
        """Add a new collection entry. Returns the new ID."""
        if entry.acquired_at is None:
            entry.acquired_at = now_iso()

        cursor = self.conn.execute(
            """
            INSERT INTO collection
            (printing_id, finish, condition, language, purchase_price,
             acquired_at, source, source_image, notes, tags, tradelist,
             is_alter, proxy, signed, misprint, status, sale_price, order_id,
             batch_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.printing_id,
                entry.finish,
                entry.condition,
                entry.language,
                entry.purchase_price,
                entry.acquired_at,
                entry.source,
                entry.source_image,
                entry.notes,
                entry.tags,
                1 if entry.tradelist else 0,
                1 if entry.alter else 0,
                1 if entry.proxy else 0,
                1 if entry.signed else 0,
                1 if entry.misprint else 0,
                entry.status,
                entry.sale_price,
                entry.order_id,
                entry.batch_id,
            ),
        )
        new_id = cursor.lastrowid
        # Log the initial status
        self.conn.execute(
            "INSERT INTO status_log (collection_id, from_status, to_status, changed_at) VALUES (?, NULL, ?, ?)",
            (new_id, entry.status, entry.acquired_at),
        )
        return new_id

    def get(self, entry_id: int) -> Optional[CollectionEntry]:
        """Get a collection entry by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM collection WHERE id = ?", (entry_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_entry(row)

    def update(self, entry: CollectionEntry, status_note: Optional[str] = None) -> bool:
        """Update a collection entry. Returns True if updated."""
        if entry.id is None:
            return False

        # Check if status changed for logging
        old = self.get(entry.id)
        old_status = old.status if old else None

        cursor = self.conn.execute(
            """
            UPDATE collection SET
                printing_id = ?,
                finish = ?,
                condition = ?,
                language = ?,
                purchase_price = ?,
                acquired_at = ?,
                source = ?,
                source_image = ?,
                notes = ?,
                tags = ?,
                tradelist = ?,
                is_alter = ?,
                proxy = ?,
                signed = ?,
                misprint = ?,
                status = ?,
                sale_price = ?,
                order_id = ?,
                batch_id = ?
            WHERE id = ?
            """,
            (
                entry.printing_id,
                entry.finish,
                entry.condition,
                entry.language,
                entry.purchase_price,
                entry.acquired_at,
                entry.source,
                entry.source_image,
                entry.notes,
                entry.tags,
                1 if entry.tradelist else 0,
                1 if entry.alter else 0,
                1 if entry.proxy else 0,
                1 if entry.signed else 0,
                1 if entry.misprint else 0,
                entry.status,
                entry.sale_price,
                entry.order_id,
                entry.batch_id,
                entry.id,
            ),
        )
        updated = cursor.rowcount > 0

        # Log status change
        if updated and old_status and old_status != entry.status:
            self.conn.execute(
                "INSERT INTO status_log (collection_id, from_status, to_status, changed_at, note) VALUES (?, ?, ?, ?, ?)",
                (entry.id, old_status, entry.status, now_iso(), status_note),
            )

        return updated

    def delete(self, entry_id: int) -> bool:
        """Delete a collection entry. Returns True if deleted."""
        cursor = self.conn.execute(
            "DELETE FROM collection WHERE id = ?", (entry_id,)
        )
        return cursor.rowcount > 0

    def list_all(
        self,
        set_code: Optional[str] = None,
        name: Optional[str] = None,
        foil: Optional[bool] = None,
        condition: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List collection entries with optional filters.
        Returns joined data with card/printing info.
        """
        query = """
            SELECT
                c.id, c.printing_id, c.finish, c.condition, c.language,
                c.purchase_price, c.acquired_at, c.source, c.notes, c.tags,
                c.tradelist, c.is_alter, c.proxy, c.signed, c.misprint,
                c.status, c.sale_price,
                p.set_code, p.collector_number, p.rarity, p.artist,
                card.name, card.type_line, card.mana_cost,
                s.set_name
            FROM collection c
            JOIN printings p ON c.printing_id = p.printing_id
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            WHERE 1=1
        """
        params = []

        if set_code:
            query += " AND p.set_code = ?"
            params.append(set_code.lower())

        if name:
            query += " AND card.name LIKE ?"
            params.append(f"%{name}%")

        if foil is not None:
            if foil:
                query += " AND c.finish IN ('foil', 'etched')"
            else:
                query += " AND c.finish = 'nonfoil'"

        if condition:
            query += " AND c.condition = ?"
            params.append(condition)

        if source:
            query += " AND c.source = ?"
            params.append(source)

        if status:
            query += " AND c.status = ?"
            params.append(status)

        query += " ORDER BY c.acquired_at DESC"

        if limit:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor]

    def receive_card(self, collection_id: int) -> bool:
        """Receive a single ordered card (flip ordered -> owned). Returns True if updated."""
        entry = self.get(collection_id)
        if entry is None or entry.status != "ordered":
            return False
        entry.status = "owned"
        return self.update(entry, status_note="card received")

    def count(self, status: Optional[str] = None) -> int:
        """Get total number of entries in collection."""
        if status:
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM collection WHERE status = ?", (status,)
            )
        else:
            cursor = self.conn.execute("SELECT COUNT(*) FROM collection")
        return cursor.fetchone()[0]

    def stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        stats = {}

        # Total count
        stats["total_cards"] = self.count()

        # By status
        cursor = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM collection GROUP BY status"
        )
        stats["by_status"] = {row["status"]: row["cnt"] for row in cursor}

        # By finish
        cursor = self.conn.execute(
            "SELECT finish, COUNT(*) as cnt FROM collection GROUP BY finish"
        )
        stats["by_finish"] = {row["finish"]: row["cnt"] for row in cursor}

        # By condition
        cursor = self.conn.execute(
            "SELECT condition, COUNT(*) as cnt FROM collection GROUP BY condition"
        )
        stats["by_condition"] = {row["condition"]: row["cnt"] for row in cursor}

        # By source
        cursor = self.conn.execute(
            "SELECT source, COUNT(*) as cnt FROM collection GROUP BY source"
        )
        stats["by_source"] = {row["source"]: row["cnt"] for row in cursor}

        # Unique printings
        cursor = self.conn.execute(
            "SELECT COUNT(DISTINCT printing_id) FROM collection"
        )
        stats["unique_printings"] = cursor.fetchone()[0]

        # Unique cards (oracle_id)
        cursor = self.conn.execute(
            """
            SELECT COUNT(DISTINCT p.oracle_id)
            FROM collection c
            JOIN printings p ON c.printing_id = p.printing_id
            """
        )
        stats["unique_cards"] = cursor.fetchone()[0]

        # Total value
        cursor = self.conn.execute(
            "SELECT SUM(purchase_price) FROM collection WHERE purchase_price IS NOT NULL"
        )
        total = cursor.fetchone()[0]
        stats["total_value"] = total if total else 0.0

        return stats

    def get_status_history(self, collection_id: int) -> List[Dict[str, Any]]:
        """Get status transition history for a collection entry."""
        cursor = self.conn.execute(
            """
            SELECT from_status, to_status, changed_at, note
            FROM status_log
            WHERE collection_id = ?
            ORDER BY changed_at ASC
            """,
            (collection_id,),
        )
        return [dict(row) for row in cursor]

    # Valid status transitions for dispose()
    VALID_TRANSITIONS = {
        'owned': {'sold', 'traded', 'gifted', 'lost', 'listed'},
        'listed': {'sold', 'owned'},
    }

    def get_copies(
        self,
        printing_id: str,
        finish: Optional[str] = None,
        condition: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return individual collection rows for a card, joined with order and lineage info."""
        query = """
            SELECT
                c.id, c.printing_id, c.finish, c.condition, c.language,
                c.purchase_price, c.acquired_at, c.source, c.source_image,
                c.notes, c.tags, c.status, c.sale_price, c.order_id,
                dc.deck_id, c.binder_id, dc.zone AS deck_zone,
                d.name AS deck_name,
                b.name AS binder_name,
                o.order_number, o.source AS order_source, o.seller_name,
                o.order_date,
                il.image_md5, il.image_path, il.card_index,
                ii.id AS image_id
            FROM collection c
            LEFT JOIN orders o ON c.order_id = o.id
            LEFT JOIN deck_cards dc ON dc.collection_id = c.id
            LEFT JOIN decks d ON dc.deck_id = d.id
            LEFT JOIN binders b ON c.binder_id = b.id
            LEFT JOIN ingest_lineage il ON il.collection_id = c.id
            LEFT JOIN ingest_images ii ON il.image_md5 = ii.md5
            WHERE c.printing_id = ?
        """
        params: List[Any] = [printing_id]

        if finish:
            query += " AND c.finish = ?"
            params.append(finish)
        if condition:
            query += " AND c.condition = ?"
            params.append(condition)
        if status:
            query += " AND c.status = ?"
            params.append(status)

        query += " ORDER BY c.acquired_at DESC"
        cursor = self.conn.execute(query, params)
        copies = []
        for row in cursor:
            copy = dict(row)
            # Attach status history
            copy['status_history'] = self.get_status_history(copy['id'])
            copies.append(copy)
        return copies

    def dispose(
        self,
        entry_id: int,
        new_status: str,
        sale_price: Optional[float] = None,
        note: Optional[str] = None,
    ) -> bool:
        """Transition a card to a disposition status (sold, traded, gifted, lost, listed).

        Validates that the transition is allowed, then updates via the existing
        update() method which handles status_log.
        """
        entry = self.get(entry_id)
        if not entry:
            raise ValueError(f"Collection entry {entry_id} not found")

        allowed = self.VALID_TRANSITIONS.get(entry.status)
        if not allowed or new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{entry.status}' to '{new_status}'"
            )

        entry.status = new_status
        if sale_price is not None:
            entry.sale_price = sale_price
        return self.update(entry, status_note=note)

    def delete_with_lineage(self, entry_id: int) -> bool:
        """Delete a collection entry and its ingest_lineage rows.

        Only allows deletion of entries with status 'owned' or 'ordered'.
        """
        entry = self.get(entry_id)
        if not entry:
            raise ValueError(f"Collection entry {entry_id} not found")
        if entry.status not in ('owned', 'ordered'):
            raise ValueError(
                f"Cannot delete entry with status '{entry.status}' — "
                "only 'owned' or 'ordered' entries can be deleted"
            )

        self.conn.execute(
            "DELETE FROM ingest_lineage WHERE collection_id = ?", (entry_id,)
        )
        return self.delete(entry_id)

    def bulk_delete(self, ids: List[int]) -> Dict[str, List[int]]:
        """Delete multiple collection entries with lineage cleanup.

        Returns dict with 'deleted' and 'skipped' ID lists.
        """
        deleted = []
        skipped = []
        for entry_id in ids:
            entry = self.get(entry_id)
            if not entry or entry.status not in ('owned', 'ordered'):
                skipped.append(entry_id)
                continue
            self.conn.execute(
                "DELETE FROM ingest_lineage WHERE collection_id = ?",
                (entry_id,),
            )
            self.delete(entry_id)
            deleted.append(entry_id)
        return {"deleted": deleted, "skipped": skipped}

    def _row_to_entry(self, row: sqlite3.Row) -> CollectionEntry:
        # Handle optional columns that might not exist in older databases
        source_image = None
        try:
            source_image = row["source_image"]
        except (IndexError, KeyError):
            pass

        status = "owned"
        try:
            status = row["status"]
        except (IndexError, KeyError):
            pass

        sale_price = None
        try:
            sale_price = row["sale_price"]
        except (IndexError, KeyError):
            pass

        order_id = None
        try:
            order_id = row["order_id"]
        except (IndexError, KeyError):
            pass

        binder_id = None
        try:
            binder_id = row["binder_id"]
        except (IndexError, KeyError):
            pass

        batch_id = None
        try:
            batch_id = row["batch_id"]
        except (IndexError, KeyError):
            pass

        return CollectionEntry(
            id=row["id"],
            printing_id=row["printing_id"],
            finish=row["finish"],
            condition=row["condition"],
            language=row["language"],
            purchase_price=row["purchase_price"],
            acquired_at=row["acquired_at"],
            source=row["source"],
            source_image=source_image,
            notes=row["notes"],
            tags=row["tags"],
            tradelist=bool(row["tradelist"]),
            alter=bool(row["is_alter"]),
            proxy=bool(row["proxy"]),
            signed=bool(row["signed"]),
            misprint=bool(row["misprint"]),
            status=status,
            sale_price=sale_price,
            order_id=order_id,
            binder_id=binder_id,
            batch_id=batch_id,
        )

    def get_movement_history(self, collection_id: int) -> List[Dict[str, Any]]:
        """Get chronological movement history for a collection entry."""
        cursor = self.conn.execute(
            """SELECT ml.*,
                      fd.name AS from_deck_name, td.name AS to_deck_name,
                      fb.name AS from_binder_name, tb.name AS to_binder_name
               FROM movement_log ml
               LEFT JOIN decks fd ON ml.from_deck_id = fd.id
               LEFT JOIN decks td ON ml.to_deck_id = td.id
               LEFT JOIN binders fb ON ml.from_binder_id = fb.id
               LEFT JOIN binders tb ON ml.to_binder_id = tb.id
               WHERE ml.collection_id = ?
               ORDER BY ml.changed_at, ml.id""",
            (collection_id,),
        )
        return [dict(row) for row in cursor]


class OrderRepository:
    """CRUD operations for orders table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, order: Order) -> int:
        """Add a new order. Returns the new ID."""
        if order.created_at is None:
            order.created_at = now_iso()

        cursor = self.conn.execute(
            """
            INSERT INTO orders
            (order_number, source, seller_name, order_date, subtotal,
             shipping, tax, total, shipping_status, estimated_delivery,
             notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order.order_number,
                order.source,
                order.seller_name,
                order.order_date,
                order.subtotal,
                order.shipping,
                order.tax,
                order.total,
                order.shipping_status,
                order.estimated_delivery,
                order.notes,
                order.created_at,
            ),
        )
        return cursor.lastrowid

    def get(self, order_id: int) -> Optional[Order]:
        """Get an order by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_order(row)

    def get_by_number(self, order_number: str) -> List[Order]:
        """Get orders by order number (may be multiple sellers per order)."""
        cursor = self.conn.execute(
            "SELECT * FROM orders WHERE order_number = ? ORDER BY seller_name",
            (order_number,),
        )
        return [self._row_to_order(row) for row in cursor]

    def list_all(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all orders with card counts and ordered counts."""
        query = """
            SELECT o.*, COUNT(c.id) as card_count,
                   SUM(CASE WHEN c.status = 'ordered' THEN 1 ELSE 0 END) as ordered_count
            FROM orders o
            LEFT JOIN collection c ON c.order_id = o.id
            WHERE 1=1
        """
        params = []
        if source:
            query += " AND o.source = ?"
            params.append(source)
        query += " GROUP BY o.id ORDER BY o.created_at DESC"

        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor]

    def get_order_cards(self, order_id: int) -> List[Dict[str, Any]]:
        """Get all collection entries for an order."""
        cursor = self.conn.execute(
            """
            SELECT c.*, card.name, p.set_code, p.collector_number, p.rarity,
                   p.image_uri, s.set_name
            FROM collection c
            JOIN printings p ON c.printing_id = p.printing_id
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            WHERE c.order_id = ?
            ORDER BY card.name
            """,
            (order_id,),
        )
        return [dict(row) for row in cursor]

    def receive_order(self, order_id: int, card_ids: Optional[List[int]] = None) -> int:
        """Batch flip ordered cards in this order to owned. Returns count.

        If card_ids is provided, only those specific collection entries are received.
        """
        ts = now_iso()
        # Get IDs of cards to update
        if card_ids:
            placeholders = ",".join("?" * len(card_ids))
            cursor = self.conn.execute(
                f"SELECT id FROM collection WHERE order_id = ? AND status = 'ordered' AND id IN ({placeholders})",
                [order_id] + card_ids,
            )
        else:
            cursor = self.conn.execute(
                "SELECT id FROM collection WHERE order_id = ? AND status = 'ordered'",
                (order_id,),
            )
        ids = [row["id"] for row in cursor]
        if not ids:
            return 0

        # Update status
        placeholders = ",".join("?" * len(ids))
        self.conn.execute(
            f"UPDATE collection SET status = 'owned' WHERE id IN ({placeholders})",
            ids,
        )

        # Log status changes
        for cid in ids:
            self.conn.execute(
                "INSERT INTO status_log (collection_id, from_status, to_status, changed_at, note) "
                "VALUES (?, 'ordered', 'owned', ?, 'order received')",
                (cid, ts),
            )

        return len(ids)

    def update(self, order: Order) -> bool:
        """Update an order. Returns True if updated."""
        cursor = self.conn.execute(
            """
            UPDATE orders SET order_number=?, source=?, seller_name=?, order_date=?,
                subtotal=?, shipping=?, tax=?, total=?,
                shipping_status=?, estimated_delivery=?, notes=?
            WHERE id = ?
            """,
            (
                order.order_number, order.source, order.seller_name, order.order_date,
                order.subtotal, order.shipping, order.tax, order.total,
                order.shipping_status, order.estimated_delivery, order.notes, order.id,
            ),
        )
        return cursor.rowcount > 0

    def _row_to_order(self, row: sqlite3.Row) -> Order:
        return Order(
            id=row["id"],
            order_number=row["order_number"],
            source=row["source"],
            seller_name=row["seller_name"],
            order_date=row["order_date"],
            subtotal=row["subtotal"],
            shipping=row["shipping"],
            tax=row["tax"],
            total=row["total"],
            shipping_status=row["shipping_status"],
            estimated_delivery=row["estimated_delivery"],
            notes=row["notes"],
            created_at=row["created_at"],
        )


class WishlistRepository:
    """CRUD operations for wishlist table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, entry: WishlistEntry) -> int:
        """Add a wishlist entry. Returns the new ID."""
        if entry.added_at is None:
            entry.added_at = now_iso()

        cursor = self.conn.execute(
            """
            INSERT INTO wishlist
            (oracle_id, printing_id, max_price, priority, notes, added_at, source, fulfilled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.oracle_id,
                entry.printing_id,
                entry.max_price,
                entry.priority,
                entry.notes,
                entry.added_at,
                entry.source,
                entry.fulfilled_at,
            ),
        )
        return cursor.lastrowid

    def get(self, entry_id: int) -> Optional[WishlistEntry]:
        """Get a wishlist entry by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM wishlist WHERE id = ?", (entry_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def update(self, entry: WishlistEntry) -> bool:
        """Update a wishlist entry. Returns True if updated."""
        if entry.id is None:
            return False
        cursor = self.conn.execute(
            """
            UPDATE wishlist SET
                oracle_id = ?, printing_id = ?, max_price = ?,
                priority = ?, notes = ?, source = ?, fulfilled_at = ?
            WHERE id = ?
            """,
            (
                entry.oracle_id,
                entry.printing_id,
                entry.max_price,
                entry.priority,
                entry.notes,
                entry.source,
                entry.fulfilled_at,
                entry.id,
            ),
        )
        return cursor.rowcount > 0

    def delete(self, entry_id: int) -> bool:
        """Delete a wishlist entry. Returns True if deleted."""
        cursor = self.conn.execute(
            "DELETE FROM wishlist WHERE id = ?", (entry_id,)
        )
        return cursor.rowcount > 0

    def fulfill(self, entry_id: int) -> bool:
        """Mark a wishlist entry as fulfilled."""
        cursor = self.conn.execute(
            "UPDATE wishlist SET fulfilled_at = ? WHERE id = ?",
            (now_iso(), entry_id),
        )
        return cursor.rowcount > 0

    def list_all(
        self,
        fulfilled: Optional[bool] = None,
        oracle_id: Optional[str] = None,
        name: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List wishlist entries with card info joined."""
        query = """
            SELECT
                w.id, w.oracle_id, w.printing_id, w.max_price,
                w.priority, w.notes, w.added_at, w.source, w.fulfilled_at,
                card.name, card.type_line, card.mana_cost,
                p.set_code, p.collector_number, p.image_uri
            FROM wishlist w
            JOIN cards card ON w.oracle_id = card.oracle_id
            LEFT JOIN printings p ON w.printing_id = p.printing_id
            WHERE 1=1
        """
        params = []

        if fulfilled is not None:
            if fulfilled:
                query += " AND w.fulfilled_at IS NOT NULL"
            else:
                query += " AND w.fulfilled_at IS NULL"

        if oracle_id:
            query += " AND w.oracle_id = ?"
            params.append(oracle_id)

        if name:
            query += " AND card.name LIKE ?"
            params.append(f"%{name}%")

        query += " ORDER BY w.priority DESC, w.added_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor]

    def count(self, fulfilled: Optional[bool] = None) -> int:
        """Count wishlist entries."""
        if fulfilled is not None:
            if fulfilled:
                cursor = self.conn.execute(
                    "SELECT COUNT(*) FROM wishlist WHERE fulfilled_at IS NOT NULL"
                )
            else:
                cursor = self.conn.execute(
                    "SELECT COUNT(*) FROM wishlist WHERE fulfilled_at IS NULL"
                )
        else:
            cursor = self.conn.execute("SELECT COUNT(*) FROM wishlist")
        return cursor.fetchone()[0]

    def _row_to_entry(self, row: sqlite3.Row) -> WishlistEntry:
        return WishlistEntry(
            id=row["id"],
            oracle_id=row["oracle_id"],
            printing_id=row["printing_id"],
            max_price=row["max_price"],
            priority=row["priority"],
            notes=row["notes"],
            added_at=row["added_at"],
            source=row["source"],
            fulfilled_at=row["fulfilled_at"],
        )


class SealedProductRepository:
    """CRUD operations for sealed_products table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, uuid: str) -> Optional[SealedProduct]:
        """Get a sealed product by UUID."""
        cursor = self.conn.execute(
            "SELECT * FROM sealed_products WHERE uuid = ?", (uuid,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_product(row)

    def get_by_tcgplayer_id(self, tcgplayer_product_id: str) -> Optional[SealedProduct]:
        """Get a sealed product by TCGPlayer product ID."""
        cursor = self.conn.execute(
            "SELECT * FROM sealed_products WHERE tcgplayer_product_id = ?",
            (tcgplayer_product_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_product(row)

    def search_by_name(self, name: str, limit: int = 20) -> List[SealedProduct]:
        """Search sealed products by name (case-insensitive, each word matched independently)."""
        words = name.split()
        if not words:
            return []
        clauses = ["name LIKE ? COLLATE NOCASE"] * len(words)
        params = [f"%{w}%" for w in words]
        params.append(limit)
        cursor = self.conn.execute(
            f"SELECT * FROM sealed_products WHERE {' AND '.join(clauses)} ORDER BY name LIMIT ?",
            params,
        )
        return [self._row_to_product(row) for row in cursor]

    def list_by_set(self, set_code: str) -> List[SealedProduct]:
        """List all sealed products for a set."""
        cursor = self.conn.execute(
            "SELECT * FROM sealed_products WHERE set_code = ? ORDER BY category, name",
            (set_code,),
        )
        return [self._row_to_product(row) for row in cursor]

    def list_sets_with_products(self) -> List[Dict[str, Any]]:
        """List sets that have sealed products, with counts."""
        cursor = self.conn.execute("""
            SELECT sp.set_code, s.set_name, COUNT(*) as product_count
            FROM sealed_products sp
            LEFT JOIN sets s ON sp.set_code = s.set_code
            GROUP BY sp.set_code
            ORDER BY s.released_at DESC
        """)
        return [dict(row) for row in cursor]

    def count(self) -> int:
        """Get total number of sealed products."""
        return self.conn.execute("SELECT COUNT(*) FROM sealed_products").fetchone()[0]

    def _row_to_product(self, row: sqlite3.Row) -> SealedProduct:
        source = "mtgjson"
        try:
            source = row["source"]
        except (IndexError, KeyError):
            pass

        return SealedProduct(
            uuid=row["uuid"],
            name=row["name"],
            set_code=row["set_code"],
            category=row["category"],
            subtype=row["subtype"],
            tcgplayer_product_id=row["tcgplayer_product_id"],
            card_count=row["card_count"],
            product_size=row["product_size"],
            release_date=row["release_date"],
            purchase_url_tcgplayer=row["purchase_url_tcgplayer"],
            purchase_url_cardkingdom=row["purchase_url_cardkingdom"],
            contents_json=row["contents_json"],
            imported_at=row["imported_at"],
            source=source,
        )


class SealedProductCardRepository:
    """Read-only access to pre-resolved sealed product card contents."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_cards_for_product(self, sealed_product_uuid: str) -> List[Dict]:
        """Get resolved card data for a sealed product.

        JOINs through mtgjson_uuid_map → printings → cards to resolve
        each card to its printing_id, name, set_code, etc.
        """
        rows = self.conn.execute("""
            SELECT
                spc.mtgjson_uuid,
                spc.quantity,
                spc.is_foil,
                spc.zone,
                spc.source_type,
                spc.source_name,
                um.set_code,
                um.collector_number,
                p.printing_id,
                p.rarity,
                p.image_uri,
                c.name AS card_name
            FROM sealed_product_cards spc
            LEFT JOIN mtgjson_uuid_map um ON spc.mtgjson_uuid = um.uuid
            LEFT JOIN printings p ON um.set_code = p.set_code
                AND um.collector_number = p.collector_number
            LEFT JOIN cards c ON p.oracle_id = c.oracle_id
            WHERE spc.sealed_product_uuid = ?
        """, (sealed_product_uuid,)).fetchall()

        result = []
        for r in rows:
            result.append({
                "mtgjson_uuid": r["mtgjson_uuid"],
                "quantity": r["quantity"],
                "is_foil": bool(r["is_foil"]),
                "zone": r["zone"],
                "source_type": r["source_type"],
                "source_name": r["source_name"],
                "set_code": r["set_code"],
                "collector_number": r["collector_number"],
                "printing_id": r["printing_id"],
                "rarity": r["rarity"],
                "image_uri": r["image_uri"],
                "name": r["card_name"],
            })
        return result

    def has_cards(self, sealed_product_uuid: str) -> bool:
        """Check if a sealed product has any pre-resolved card contents."""
        row = self.conn.execute(
            "SELECT 1 FROM sealed_product_cards WHERE sealed_product_uuid = ? LIMIT 1",
            (sealed_product_uuid,),
        ).fetchone()
        return row is not None

    def card_count(self, sealed_product_uuid: str) -> int:
        """Get total card count (sum of quantities) for a sealed product."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM sealed_product_cards WHERE sealed_product_uuid = ?",
            (sealed_product_uuid,),
        ).fetchone()
        return row[0]


class SealedCollectionRepository:
    """CRUD operations for sealed_collection table."""

    VALID_TRANSITIONS = {
        'owned': {'sold', 'traded', 'gifted', 'listed', 'opened'},
        'listed': {'sold', 'owned'},
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, entry: SealedCollectionEntry) -> int:
        """Add a sealed product to the collection. Returns the new ID."""
        if entry.added_at is None:
            entry.added_at = now_iso()
        cursor = self.conn.execute(
            """
            INSERT INTO sealed_collection
            (sealed_product_uuid, quantity, condition, purchase_price, purchase_date,
             source, seller_name, notes, status, sale_price, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.sealed_product_uuid,
                entry.quantity,
                entry.condition,
                entry.purchase_price,
                entry.purchase_date,
                entry.source,
                entry.seller_name,
                entry.notes,
                entry.status,
                entry.sale_price,
                entry.added_at,
            ),
        )
        return cursor.lastrowid

    def get(self, entry_id: int) -> Optional[SealedCollectionEntry]:
        """Get a sealed collection entry by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM sealed_collection WHERE id = ?", (entry_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def update(self, entry: SealedCollectionEntry) -> bool:
        """Update a sealed collection entry. Returns True if updated."""
        if entry.id is None:
            return False
        cursor = self.conn.execute(
            """
            UPDATE sealed_collection SET
                sealed_product_uuid = ?, quantity = ?, condition = ?,
                purchase_price = ?, purchase_date = ?, source = ?,
                seller_name = ?, notes = ?, status = ?, sale_price = ?
            WHERE id = ?
            """,
            (
                entry.sealed_product_uuid,
                entry.quantity,
                entry.condition,
                entry.purchase_price,
                entry.purchase_date,
                entry.source,
                entry.seller_name,
                entry.notes,
                entry.status,
                entry.sale_price,
                entry.id,
            ),
        )
        return cursor.rowcount > 0

    def delete(self, entry_id: int) -> bool:
        """Delete a sealed collection entry. Returns True if deleted."""
        cursor = self.conn.execute(
            "DELETE FROM sealed_collection WHERE id = ?", (entry_id,)
        )
        return cursor.rowcount > 0

    def list_all(
        self,
        set_code: Optional[str] = None,
        category: Optional[str] = None,
        subtype: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List sealed collection entries with product info and latest prices."""
        query = """
            SELECT
                sc.id, sc.sealed_product_uuid, sc.quantity, sc.condition,
                sc.purchase_price, sc.purchase_date, sc.source, sc.seller_name,
                sc.notes, sc.status, sc.sale_price, sc.added_at,
                sp.name, sp.set_code, sp.category, sp.subtype,
                sp.tcgplayer_product_id, sp.card_count, sp.release_date,
                sp.purchase_url_tcgplayer, sp.purchase_url_cardkingdom,
                sp.contents_json,
                s.set_name,
                lsp.market_price, lsp.low_price, lsp.mid_price, lsp.high_price
            FROM sealed_collection sc
            JOIN sealed_products sp ON sc.sealed_product_uuid = sp.uuid
            LEFT JOIN sets s ON sp.set_code = s.set_code
            LEFT JOIN latest_sealed_prices lsp ON sp.tcgplayer_product_id = lsp.tcgplayer_product_id
            WHERE 1=1
        """
        params: List[Any] = []

        if set_code:
            query += " AND sp.set_code = ?"
            params.append(set_code.lower())
        if category:
            query += " AND sp.category = ?"
            params.append(category)
        if subtype:
            query += " AND sp.subtype = ?"
            params.append(subtype)
        if status:
            query += " AND sc.status = ?"
            params.append(status)

        query += " ORDER BY sc.added_at DESC"
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor]

    def dispose(
        self,
        entry_id: int,
        new_status: str,
        sale_price: Optional[float] = None,
        quantity: Optional[int] = None,
    ) -> bool:
        """Transition a sealed product to a disposition status.

        If *quantity* is given and less than the entry's current quantity,
        the entry is split: the original keeps the remainder and a new
        entry is created with the disposed quantity and new status.
        """
        entry = self.get(entry_id)
        if not entry:
            raise ValueError(f"Sealed collection entry {entry_id} not found")

        allowed = self.VALID_TRANSITIONS.get(entry.status)
        if not allowed or new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{entry.status}' to '{new_status}'"
            )

        if quantity is not None and quantity < entry.quantity:
            if quantity < 1:
                raise ValueError("quantity must be at least 1")
            # Split: decrement original, create new entry with new status
            entry.quantity -= quantity
            self.update(entry)
            split = SealedCollectionEntry(
                id=None,
                sealed_product_uuid=entry.sealed_product_uuid,
                quantity=quantity,
                condition=entry.condition,
                purchase_price=entry.purchase_price,
                purchase_date=entry.purchase_date,
                source=entry.source,
                seller_name=entry.seller_name,
                notes=entry.notes,
                status=new_status,
                sale_price=sale_price,
            )
            self.add(split)
            return True

        entry.status = new_status
        if sale_price is not None:
            entry.sale_price = sale_price
        return self.update(entry)

    def bulk_dispose(
        self,
        entry_ids: List[int],
        new_status: str,
        sale_price: Optional[float] = None,
    ) -> Dict[str, List[int]]:
        """Bulk-transition sealed products to a disposition status.

        Skips entries that are not found or cannot transition to new_status.
        Returns dict with 'disposed' and 'skipped' ID lists.
        """
        disposed = []
        skipped = []
        for entry_id in entry_ids:
            entry = self.get(entry_id)
            if not entry:
                skipped.append(entry_id)
                continue
            allowed = self.VALID_TRANSITIONS.get(entry.status)
            if not allowed or new_status not in allowed:
                skipped.append(entry_id)
                continue
            entry.status = new_status
            if sale_price is not None:
                entry.sale_price = sale_price
            self.update(entry)
            disposed.append(entry_id)
        return {"disposed": disposed, "skipped": skipped}

    ACTIVE_STATUSES = ('owned', 'listed')

    def stats(self) -> Dict[str, Any]:
        """Get sealed collection statistics.

        Totals (entries, quantity, cost, value) only count active
        inventory (owned/listed).  Disposed items are tracked in
        by_status but excluded from headline numbers.
        """
        stats: Dict[str, Any] = {}
        stats["total_entries"] = self.conn.execute(
            "SELECT COUNT(*) FROM sealed_collection"
            " WHERE status IN ('owned', 'listed')"
        ).fetchone()[0]
        stats["total_quantity"] = self.conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM sealed_collection"
            " WHERE status IN ('owned', 'listed')"
        ).fetchone()[0]

        cursor = self.conn.execute(
            "SELECT status, COUNT(*) as cnt, SUM(quantity) as qty FROM sealed_collection GROUP BY status"
        )
        stats["by_status"] = {row["status"]: {"count": row["cnt"], "quantity": row["qty"]} for row in cursor}

        total_cost = self.conn.execute(
            "SELECT COALESCE(SUM(purchase_price * quantity), 0)"
            " FROM sealed_collection"
            " WHERE purchase_price IS NOT NULL"
            " AND status IN ('owned', 'listed')"
        ).fetchone()[0]
        stats["total_cost"] = total_cost

        market_value = self.conn.execute(
            """SELECT COALESCE(SUM(lsp.market_price * sc.quantity), 0)
            FROM sealed_collection sc
            JOIN sealed_products sp ON sc.sealed_product_uuid = sp.uuid
            LEFT JOIN latest_sealed_prices lsp ON sp.tcgplayer_product_id = lsp.tcgplayer_product_id
            WHERE sc.status IN ('owned', 'listed')"""
        ).fetchone()[0]
        stats["market_value"] = market_value
        stats["gain_loss"] = market_value - total_cost

        return stats

    def _row_to_entry(self, row: sqlite3.Row) -> SealedCollectionEntry:
        return SealedCollectionEntry(
            id=row["id"],
            sealed_product_uuid=row["sealed_product_uuid"],
            quantity=row["quantity"],
            condition=row["condition"],
            purchase_price=row["purchase_price"],
            purchase_date=row["purchase_date"],
            source=row["source"],
            seller_name=row["seller_name"],
            notes=row["notes"],
            status=row["status"],
            sale_price=row["sale_price"],
            added_at=row["added_at"],
        )


def _log_movement(conn, collection_id, from_deck_id, to_deck_id,
                  from_binder_id, to_binder_id, from_zone, to_zone, note=None):
    """Insert an append-only movement_log entry."""
    conn.execute(
        "INSERT INTO movement_log (collection_id, from_deck_id, to_deck_id, "
        "from_binder_id, to_binder_id, from_zone, to_zone, changed_at, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (collection_id, from_deck_id, to_deck_id,
         from_binder_id, to_binder_id, from_zone, to_zone, now_iso(), note),
    )


class DeckRepository:
    """CRUD operations for decks table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, deck: Deck) -> int:
        ts = now_iso()
        is_precon = 1 if (deck.is_precon or deck.origin_set_code) else 0
        cursor = self.conn.execute(
            """INSERT INTO decks (name, description, format, is_precon,
               sleeve_color, deck_box, storage_location,
               origin_set_code, origin_theme, origin_variation,
               state_id, commander_oracle_id, commander_printing_id,
               plan, sub_plans, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (deck.name, deck.description, deck.format, is_precon,
             deck.sleeve_color, deck.deck_box, deck.storage_location,
             deck.origin_set_code, deck.origin_theme, deck.origin_variation,
             deck.state_id, deck.commander_oracle_id,
             deck.commander_printing_id, deck.plan, deck.sub_plans, ts, ts),
        )
        return cursor.lastrowid

    def get(self, deck_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """SELECT d.*, ds.name AS state,
                      (SELECT COUNT(*) FROM deck_cards dc WHERE dc.deck_id = d.id) as card_count,
                      (SELECT COALESCE(SUM(c.purchase_price), 0)
                       FROM deck_cards dc2
                       JOIN collection c ON dc2.collection_id = c.id
                       WHERE dc2.deck_id = d.id) as total_value,
                      (SELECT COALESCE(SUM(e.quantity), 0)
                       FROM deck_expected_cards e WHERE e.deck_id = d.id) as expected_card_count
               FROM decks d
               JOIN deck_states ds ON d.state_id = ds.id
               WHERE d.id = ?""",
            (deck_id,),
        ).fetchone()
        return dict(row) if row else None

    def update(self, deck_id: int, data: Dict[str, Any]) -> bool:
        fields = []
        params = []
        allowed = ("name", "description", "format", "is_precon",
                    "sleeve_color", "deck_box", "storage_location",
                    "origin_set_code", "origin_theme", "origin_variation",
                    "state_id",
                    "commander_oracle_id", "commander_printing_id",
                    "plan", "sub_plans")
        for key in allowed:
            if key in data:
                fields.append(f"{key} = ?")
                val = data[key]
                if key == "is_precon":
                    val = 1 if val else 0
                params.append(val)
        # Auto-set is_precon when origin_set_code is provided
        if "origin_set_code" in data and data["origin_set_code"]:
            if "is_precon" not in data:
                fields.append("is_precon = ?")
                params.append(1)
        if not fields:
            return False
        fields.append("updated_at = ?")
        params.append(now_iso())
        params.append(deck_id)
        cursor = self.conn.execute(
            f"UPDATE decks SET {', '.join(fields)} WHERE id = ?", params
        )
        return cursor.rowcount > 0

    def delete(self, deck_id: int) -> bool:
        # Log movements before deleting deck_cards rows
        rows = self.conn.execute(
            "SELECT collection_id, zone FROM deck_cards WHERE deck_id = ? AND collection_id IS NOT NULL",
            (deck_id,),
        ).fetchall()
        for row in rows:
            _log_movement(self.conn, row["collection_id"], deck_id, None,
                          None, None, row["zone"], None, note="deck deleted")
        # Explicitly delete deck_cards (don't rely on CASCADE needing PRAGMA foreign_keys)
        self.conn.execute("DELETE FROM deck_cards WHERE deck_id = ?", (deck_id,))
        cursor = self.conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
        return cursor.rowcount > 0

    def list_all(self) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            """SELECT d.*, ds.name AS state,
                      (SELECT COUNT(*) FROM deck_cards dc WHERE dc.deck_id = d.id) as card_count,
                      (SELECT COALESCE(SUM(c.purchase_price), 0)
                       FROM deck_cards dc2
                       JOIN collection c ON dc2.collection_id = c.id
                       WHERE dc2.deck_id = d.id) as total_value,
                      (CASE WHEN d.state_id = 3
                            THEN (SELECT GROUP_CONCAT(color || ':' || cnt)
                                  FROM (SELECT je.value AS color, COUNT(*) AS cnt
                                        FROM deck_cards dc3
                                        JOIN printings p ON dc3.printing_id = p.printing_id
                                        JOIN cards card ON p.oracle_id = card.oracle_id,
                                             json_each(card.colors) je
                                        WHERE dc3.deck_id = d.id
                                        GROUP BY je.value
                                        ORDER BY cnt DESC))
                            ELSE (SELECT GROUP_CONCAT(color || ':' || cnt)
                                  FROM (SELECT je.value AS color, COUNT(*) AS cnt
                                        FROM deck_expected_cards e3
                                        JOIN printings p ON e3.printing_id = p.printing_id
                                        JOIN cards card ON p.oracle_id = card.oracle_id,
                                             json_each(card.colors) je
                                        WHERE e3.deck_id = d.id
                                        GROUP BY je.value
                                        ORDER BY cnt DESC))
                       END) as deck_colors,
                      (SELECT COALESCE(SUM(e.quantity), 0)
                       FROM deck_expected_cards e WHERE e.deck_id = d.id) as expected_card_count
               FROM decks d
               JOIN deck_states ds ON d.state_id = ds.id
               ORDER BY d.name"""
        )
        return [dict(row) for row in cursor]

    def find_by_origin(self, origin_set_code: str, origin_theme: str,
                       origin_variation: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Find a deck by its origin metadata (set code + theme + optional variation)."""
        if origin_variation is not None:
            row = self.conn.execute(
                """SELECT d.*, ds.name AS state,
                          (SELECT COUNT(*) FROM deck_cards dc WHERE dc.deck_id = d.id) as card_count,
                          (SELECT COALESCE(SUM(c.purchase_price), 0)
                           FROM deck_cards dc2 JOIN collection c ON dc2.collection_id = c.id
                           WHERE dc2.deck_id = d.id) as total_value
                   FROM decks d
                   JOIN deck_states ds ON d.state_id = ds.id
                   WHERE d.origin_set_code = ? AND d.origin_theme = ? AND d.origin_variation = ?
                   LIMIT 1""",
                (origin_set_code, origin_theme, origin_variation),
            ).fetchone()
        else:
            row = self.conn.execute(
                """SELECT d.*, ds.name AS state,
                          (SELECT COUNT(*) FROM deck_cards dc WHERE dc.deck_id = d.id) as card_count,
                          (SELECT COALESCE(SUM(c.purchase_price), 0)
                           FROM deck_cards dc2 JOIN collection c ON dc2.collection_id = c.id
                           WHERE dc2.deck_id = d.id) as total_value
                   FROM decks d
                   JOIN deck_states ds ON d.state_id = ds.id
                   WHERE d.origin_set_code = ? AND d.origin_theme = ?
                   LIMIT 1""",
                (origin_set_code, origin_theme),
            ).fetchone()
        return dict(row) if row else None

    def get_cards(self, deck_id: int, zone: Optional[str] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT c.id, dc.printing_id, c.finish, c.condition, c.language,
                   c.purchase_price, c.acquired_at, dc.zone AS deck_zone,
                   dc.quantity,
                   p.set_code, p.collector_number, p.rarity, p.artist,
                   p.image_uri, p.frame_effects, p.border_color, p.full_art,
                   p.promo, p.promo_types, p.finishes,
                   card.name, card.type_line, card.mana_cost, card.cmc,
                   card.colors, card.color_identity, p.oracle_id,
                   json_extract(p.raw_json, '$.layout') as layout,
                   s.set_name
            FROM deck_cards dc
            JOIN printings p ON dc.printing_id = p.printing_id
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            LEFT JOIN collection c ON dc.collection_id = c.id
            WHERE dc.deck_id = ?
        """
        params: list = [deck_id]
        if zone:
            query += " AND dc.zone = ?"
            params.append(zone)
        query += " ORDER BY card.name"
        return [dict(row) for row in self.conn.execute(query, params)]

    def adjust_card_quantity(self, deck_id: int, printing_id: str,
                             zone: str, delta: int) -> Dict[str, Any]:
        """Adjust the quantity of a card in a deck by +1 or -1.

        Works for all deck states:
        - Idea/ready: adjusts quantity in deck_expected_cards.
        - Constructed: adds/removes a physical collection entry in deck_cards.

        Returns {ok, new_qty} or raises ValueError.
        """
        if delta not in (1, -1):
            raise ValueError("delta must be +1 or -1")
        row = self.conn.execute(
            "SELECT state_id FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        if not row:
            raise ValueError("Deck not found")
        state_id = row["state_id"]

        if state_id != DECK_STATE_CONSTRUCTED:
            # Idea/ready: adjust quantity in deck_expected_cards
            row = self.conn.execute(
                "SELECT id, quantity FROM deck_expected_cards "
                "WHERE deck_id = ? AND printing_id = ? AND zone = ?",
                (deck_id, printing_id, zone),
            ).fetchone()
            if delta == 1:
                if row:
                    new_qty = row["quantity"] + 1
                    self.conn.execute(
                        "UPDATE deck_expected_cards SET quantity = ? WHERE id = ?",
                        (new_qty, row["id"]),
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO deck_expected_cards (deck_id, printing_id, zone, quantity) "
                        "VALUES (?, ?, ?, 1)",
                        (deck_id, printing_id, zone),
                    )
                    new_qty = 1
            else:  # delta == -1
                if not row or row["quantity"] <= 0:
                    raise ValueError("Card not in deck")
                new_qty = row["quantity"] - 1
                if new_qty <= 0:
                    self.conn.execute(
                        "DELETE FROM deck_expected_cards WHERE id = ?",
                        (row["id"],),
                    )
                    new_qty = 0
                else:
                    self.conn.execute(
                        "UPDATE deck_expected_cards SET quantity = ? WHERE id = ?",
                        (new_qty, row["id"]),
                    )
            return {"ok": True, "new_qty": new_qty}

        else:
            # Constructed: add/remove physical collection entries
            if delta == -1:
                # Remove one deck_cards row for this printing_id
                row = self.conn.execute(
                    "SELECT dc.id, dc.collection_id, dc.zone FROM deck_cards dc "
                    "WHERE dc.deck_id = ? AND dc.printing_id = ? AND dc.zone = ? "
                    "LIMIT 1",
                    (deck_id, printing_id, zone),
                ).fetchone()
                if not row:
                    raise ValueError("Card not in deck")
                self.conn.execute("DELETE FROM deck_cards WHERE id = ?", (row["id"],))
                if row["collection_id"]:
                    _log_movement(self.conn, row["collection_id"],
                                  from_deck_id=deck_id, to_deck_id=None,
                                  from_binder_id=None, to_binder_id=None,
                                  from_zone=row["zone"], to_zone=None,
                                  note="quantity adjust -1")
                remaining = self.conn.execute(
                    "SELECT COUNT(*) as cnt FROM deck_cards "
                    "WHERE deck_id = ? AND printing_id = ? AND zone = ?",
                    (deck_id, printing_id, zone),
                ).fetchone()["cnt"]
                return {"ok": True, "new_qty": remaining}

            else:  # delta == +1
                # Find an unassigned owned copy (same oracle_id, not in a constructed deck or binder)
                oracle_id = self.conn.execute(
                    "SELECT oracle_id FROM printings WHERE printing_id = ?",
                    (printing_id,),
                ).fetchone()
                if not oracle_id:
                    raise ValueError("Unknown printing")
                oracle_id = oracle_id["oracle_id"]
                candidate = self.conn.execute(
                    "SELECT col.id, col.printing_id FROM collection col "
                    "JOIN printings p ON col.printing_id = p.printing_id "
                    "WHERE p.oracle_id = ? AND col.status = 'owned' "
                    "AND col.binder_id IS NULL "
                    "AND NOT EXISTS ("
                    "  SELECT 1 FROM deck_cards dc "
                    "  JOIN decks d ON dc.deck_id = d.id "
                    "  WHERE dc.collection_id = col.id AND d.state_id = ?) "
                    "ORDER BY CASE WHEN col.printing_id = ? THEN 0 ELSE 1 END, col.id "
                    "LIMIT 1",
                    (oracle_id, DECK_STATE_CONSTRUCTED, printing_id),
                ).fetchone()
                if not candidate:
                    raise ValueError("No unassigned copy available")
                self.add_cards(deck_id, [candidate["id"]], zone=zone)
                current = self.conn.execute(
                    "SELECT COUNT(*) as cnt FROM deck_cards "
                    "WHERE deck_id = ? AND printing_id = ? AND zone = ?",
                    (deck_id, printing_id, zone),
                ).fetchone()["cnt"]
                return {"ok": True, "new_qty": current}

    def get_cards_for_state(self, deck_id: int, zone: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return cards for a deck, branching on state.

        Idea/ready decks read from deck_expected_cards.
        Constructed decks read from deck_cards (physical assignments).
        """
        row = self.conn.execute(
            "SELECT state_id FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        if not row or row["state_id"] == DECK_STATE_CONSTRUCTED:
            return self.get_cards(deck_id, zone=zone)

        query = """
            SELECT NULL as id, e.printing_id, 'nonfoil' as finish,
                   NULL as condition, NULL as language,
                   NULL as purchase_price, NULL as acquired_at,
                   e.zone AS deck_zone, e.quantity,
                   p.set_code, p.collector_number, p.rarity, p.artist,
                   p.image_uri, p.frame_effects, p.border_color, p.full_art,
                   p.promo, p.promo_types, p.finishes,
                   card.name, card.type_line, card.mana_cost, card.cmc,
                   card.colors, card.color_identity, p.oracle_id,
                   json_extract(p.raw_json, '$.layout') as layout,
                   s.set_name
            FROM deck_expected_cards e
            JOIN printings p ON e.printing_id = p.printing_id
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            WHERE e.deck_id = ?
        """
        params: list = [deck_id]
        if zone:
            query += " AND e.zone = ?"
            params.append(zone)
        query += " ORDER BY card.name"
        return [dict(row) for row in self.conn.execute(query, params)]

    def add_expected_cards(self, deck_id: int, printing_ids: List[str],
                           zone: str = "mainboard") -> int:
        """Add cards to an idea/ready deck's expected list."""
        count = 0
        for pid in printing_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO deck_expected_cards (deck_id, printing_id, zone, quantity) "
                "VALUES (?, ?, ?, 1)",
                (deck_id, pid, zone),
            )
            count += self.conn.execute("SELECT changes()").fetchone()[0]
        return count

    def remove_expected_cards(self, deck_id: int, printing_ids: List[str]) -> int:
        """Remove cards from an idea/ready deck's expected list."""
        if not printing_ids:
            return 0
        placeholders = ",".join("?" * len(printing_ids))
        cursor = self.conn.execute(
            f"DELETE FROM deck_expected_cards WHERE deck_id = ? AND printing_id IN ({placeholders})",
            [deck_id] + printing_ids,
        )
        return cursor.rowcount

    def remove_expected_cards_by_oracle(self, deck_id: int, oracle_id: str,
                                        zone: str) -> int:
        """Remove all expected entries for a given oracle_id+zone.

        Completeness reports group by oracle_id, so the UI only has an
        oracle_id when asking to drop a missing/present/extra entry. This
        sweeps every printing of that card from the expected list.
        """
        cursor = self.conn.execute(
            "DELETE FROM deck_expected_cards "
            "WHERE deck_id = ? AND zone = ? AND printing_id IN ("
            "  SELECT printing_id FROM printings WHERE oracle_id = ?"
            ")",
            (deck_id, zone, oracle_id),
        )
        return cursor.rowcount

    def add_cards(self, deck_id: int, collection_ids: List[int],
                  zone: str = "mainboard") -> int:
        if not collection_ids:
            return 0
        placeholders = ",".join("?" * len(collection_ids))
        # Check for deck conflicts (only block cards in constructed decks)
        deck_conflicts = self.conn.execute(
            f"SELECT dc.collection_id FROM deck_cards dc "
            f"JOIN decks d ON dc.deck_id = d.id "
            f"WHERE dc.collection_id IN ({placeholders}) "
            f"AND d.state_id = {DECK_STATE_CONSTRUCTED}",
            collection_ids,
        ).fetchall()
        # Check for binder conflicts
        binder_conflicts = self.conn.execute(
            f"SELECT id FROM collection "
            f"WHERE id IN ({placeholders}) AND binder_id IS NOT NULL",
            collection_ids,
        ).fetchall()
        conflict_ids = [r["collection_id"] for r in deck_conflicts] + [r["id"] for r in binder_conflicts]
        if conflict_ids:
            raise ValueError(f"Cards already assigned to a deck or binder: {conflict_ids}")
        # Get printing_ids for the collection entries
        rows = self.conn.execute(
            f"SELECT id, printing_id FROM collection WHERE id IN ({placeholders})",
            collection_ids,
        ).fetchall()
        count = 0
        for row in rows:
            self.conn.execute(
                "INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone, quantity) "
                "VALUES (?, ?, ?, ?, 1)",
                (deck_id, row["printing_id"], row["id"], zone),
            )
            _log_movement(self.conn, row["id"], None, deck_id, None, None, None, zone)
            count += 1
        return count

    def remove_cards(self, deck_id: int, collection_ids: List[int]) -> int:
        if not collection_ids:
            return 0
        placeholders = ",".join("?" * len(collection_ids))
        # Read current zones before deleting
        rows = self.conn.execute(
            f"SELECT collection_id, zone FROM deck_cards "
            f"WHERE deck_id = ? AND collection_id IN ({placeholders})",
            [deck_id] + collection_ids,
        ).fetchall()
        cursor = self.conn.execute(
            f"DELETE FROM deck_cards "
            f"WHERE deck_id = ? AND collection_id IN ({placeholders})",
            [deck_id] + collection_ids,
        )
        for row in rows:
            _log_movement(self.conn, row["collection_id"], deck_id, None,
                          None, None, row["zone"], None)
        return cursor.rowcount

    def move_cards(self, collection_ids: List[int], target_deck_id: int,
                   zone: str = "mainboard") -> int:
        if not collection_ids:
            return 0
        placeholders = ",".join("?" * len(collection_ids))
        # Read current state before moving
        rows = self.conn.execute(
            f"SELECT c.id, dc.deck_id, c.binder_id, dc.zone AS deck_zone, c.printing_id "
            f"FROM collection c "
            f"LEFT JOIN deck_cards dc ON dc.collection_id = c.id "
            f"WHERE c.id IN ({placeholders})",
            collection_ids,
        ).fetchall()
        count = 0
        for row in rows:
            cid = row["id"]
            # Remove from old deck if any
            if row["deck_id"]:
                self.conn.execute(
                    "DELETE FROM deck_cards WHERE collection_id = ?", (cid,)
                )
            # Clear binder if any
            if row["binder_id"]:
                self.conn.execute(
                    "UPDATE collection SET binder_id = NULL WHERE id = ?", (cid,)
                )
            # Add to target deck
            self.conn.execute(
                "INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone, quantity) "
                "VALUES (?, ?, ?, ?, 1)",
                (target_deck_id, row["printing_id"], cid, zone),
            )
            _log_movement(self.conn, cid, row["deck_id"], target_deck_id,
                          row["binder_id"], None, row["deck_zone"], zone)
            count += 1
        return count


    def set_expected_cards(self, deck_id: int, cards: List[Dict]) -> int:
        """Replace the expected card list for a deck.

        Each dict: {printing_id, zone, quantity}.
        Returns number of cards inserted.
        """
        self.conn.execute(
            "DELETE FROM deck_expected_cards WHERE deck_id = ?", (deck_id,)
        )
        count = 0
        for card in cards:
            self.conn.execute(
                "INSERT INTO deck_expected_cards (deck_id, printing_id, zone, quantity) "
                "VALUES (?, ?, ?, ?)",
                (deck_id, card["printing_id"], card.get("zone", "mainboard"),
                 card.get("quantity", 1)),
            )
            count += 1
        return count

    def get_expected_cards(self, deck_id: int) -> List[Dict]:
        """Return the expected card list with card names joined via printing."""
        rows = self.conn.execute(
            "SELECT e.printing_id, p.oracle_id, c.name, p.set_code, p.collector_number, e.zone, e.quantity "
            "FROM deck_expected_cards e "
            "JOIN printings p ON e.printing_id = p.printing_id "
            "JOIN cards c ON p.oracle_id = c.oracle_id "
            "WHERE e.deck_id = ? ORDER BY c.name",
            (deck_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_expected_cards_as_cards(self, deck_id: int) -> List[Dict]:
        """Return expected cards with full printing data, shaped like get_cards() output.

        Since printing_id is stored directly, this is a simple join.
        Cards with quantity > 1 produce one row with a quantity field.
        """
        rows = self.conn.execute(
            """SELECT p.oracle_id, e.zone, e.quantity,
                      card.name, card.type_line, card.mana_cost, card.cmc,
                      card.colors, card.color_identity,
                      p.printing_id, p.set_code, p.collector_number,
                      p.rarity, p.artist, p.image_uri,
                      p.frame_effects, p.border_color, p.full_art,
                      p.promo, p.promo_types, p.finishes,
                      json_extract(p.raw_json, '$.layout') as layout,
                      s.set_name
               FROM deck_expected_cards e
               JOIN printings p ON e.printing_id = p.printing_id
               JOIN cards card ON p.oracle_id = card.oracle_id
               JOIN sets s ON p.set_code = s.set_code
               WHERE e.deck_id = ?
               ORDER BY card.name""",
            (deck_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["deck_zone"] = d.pop("zone")
            d["id"] = None
            d["finish"] = "nonfoil"
            d["condition"] = None
            d["language"] = None
            d["purchase_price"] = None
            d["acquired_at"] = None
            result.append(d)
        return result

    def get_deck_completeness(self, deck_id: int) -> Dict:
        """Compare expected cards against actual deck contents.

        Returns {present, missing, extra} with location info for missing cards.
        """
        expected = self.conn.execute(
            "SELECT p.oracle_id, c.name, e.zone, e.quantity "
            "FROM deck_expected_cards e "
            "JOIN printings p ON e.printing_id = p.printing_id "
            "JOIN cards c ON p.oracle_id = c.oracle_id "
            "WHERE e.deck_id = ?",
            (deck_id,),
        ).fetchall()

        # Count actual cards by oracle_id+zone in this deck
        actual_rows = self.conn.execute(
            "SELECT p.oracle_id, card.name, dc.zone AS deck_zone, COUNT(*) as qty "
            "FROM deck_cards dc "
            "JOIN printings p ON dc.printing_id = p.printing_id "
            "JOIN cards card ON p.oracle_id = card.oracle_id "
            "WHERE dc.deck_id = ? AND dc.collection_id IS NOT NULL "
            "GROUP BY p.oracle_id, dc.zone",
            (deck_id,),
        ).fetchall()
        actual_map: Dict[str, int] = {}
        actual_names: Dict[str, str] = {}
        for r in actual_rows:
            key = f"{r['oracle_id']}|{r['deck_zone']}"
            actual_map[key] = r["qty"]
            actual_names[r["oracle_id"]] = r["name"]

        expected_keys = set()
        present = []
        missing = []

        for r in expected:
            key = f"{r['oracle_id']}|{r['zone']}"
            expected_keys.add(key)
            actual_qty = actual_map.get(key, 0)
            entry = {
                "oracle_id": r["oracle_id"], "name": r["name"],
                "zone": r["zone"], "expected_qty": r["quantity"],
                "actual_qty": actual_qty,
            }
            if actual_qty >= r["quantity"]:
                present.append(entry)
            else:
                # Find where missing copies are in the collection
                locations = self.conn.execute(
                    "SELECT col.id as collection_id, "
                    "d.name as deck_name, b.name as binder_name, col.status "
                    "FROM collection col "
                    "JOIN printings p ON col.printing_id = p.printing_id "
                    "LEFT JOIN deck_cards dc ON dc.collection_id = col.id "
                    "LEFT JOIN decks d ON dc.deck_id = d.id "
                    "LEFT JOIN binders b ON col.binder_id = b.id "
                    "WHERE p.oracle_id = ? AND (dc.deck_id IS NULL OR dc.deck_id != ?)",
                    (r["oracle_id"], deck_id),
                ).fetchall()
                entry["locations"] = [dict(loc) for loc in locations]
                missing.append(entry)

        # Extra: cards in the deck not on the expected list
        extra = []
        for r in actual_rows:
            key = f"{r['oracle_id']}|{r['deck_zone']}"
            if key not in expected_keys:
                extra.append({
                    "oracle_id": r["oracle_id"], "name": r["name"],
                    "zone": r["deck_zone"], "actual_qty": r["qty"],
                })

        return {"present": present, "missing": missing, "extra": extra}

    def materialize_deck(self, deck_id: int) -> Dict:
        """Convert an idea/ready deck to constructed by assigning owned, unassigned collection entries.

        For each expected card, prefers the same printing, then FIFO.
        Returns {matched: [...], missing: [...], total_matched, total_missing}.
        """
        expected = self.get_expected_cards(deck_id)
        matched = []
        missing = []
        # Group collection_ids by zone for batch add_cards calls
        zone_ids: Dict[str, List[int]] = {}

        for exp in expected:
            rows = self.conn.execute(
                "SELECT col.id, col.printing_id FROM collection col "
                "JOIN printings p ON col.printing_id = p.printing_id "
                "WHERE p.oracle_id = ? AND col.status = 'owned' "
                "AND col.binder_id IS NULL "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM deck_cards dc "
                "  JOIN decks d ON dc.deck_id = d.id "
                "  WHERE dc.collection_id = col.id AND d.state_id = ?"
                ") "
                "ORDER BY CASE WHEN col.printing_id = ? THEN 0 ELSE 1 END, col.id "
                "LIMIT ?",
                (exp["oracle_id"], DECK_STATE_CONSTRUCTED, exp["printing_id"], exp["quantity"]),
            ).fetchall()

            found_ids = [r["id"] for r in rows]
            zone = exp["zone"]
            entry = {
                "name": exp["name"],
                "oracle_id": exp["oracle_id"],
                "printing_id": exp["printing_id"],
                "zone": zone,
                "expected": exp["quantity"],
                "found": len(found_ids),
            }

            if found_ids:
                zone_ids.setdefault(zone, []).extend(found_ids)
                matched.append(entry)
            if len(found_ids) < exp["quantity"]:
                entry_missing = dict(entry)
                entry_missing["short"] = exp["quantity"] - len(found_ids)
                missing.append(entry_missing)
            elif not found_ids:
                missing.append(entry)

        # Clear any existing deck_cards for this deck before re-assigning
        self.conn.execute(
            "DELETE FROM deck_cards WHERE deck_id = ?",
            (deck_id,),
        )

        for zone, ids in zone_ids.items():
            self.add_cards(deck_id, ids, zone=zone)

        self.update(deck_id, {"state_id": DECK_STATE_CONSTRUCTED})

        total_matched = sum(len(ids) for ids in zone_ids.values())
        total_missing = sum(
            e["expected"] - e["found"] for e in missing
        )
        return {
            "matched": matched,
            "missing": missing,
            "total_matched": total_matched,
            "total_missing": total_missing,
        }


class BinderRepository:
    """CRUD operations for binders table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, binder: Binder) -> int:
        ts = now_iso()
        cursor = self.conn.execute(
            """INSERT INTO binders (name, description, color, binder_type,
               storage_location, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (binder.name, binder.description, binder.color,
             binder.binder_type, binder.storage_location, ts, ts),
        )
        return cursor.lastrowid

    def get(self, binder_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """SELECT b.*,
                      COUNT(c.id) as card_count,
                      COALESCE(SUM(c.purchase_price), 0) as total_value
               FROM binders b
               LEFT JOIN collection c ON c.binder_id = b.id
               WHERE b.id = ?
               GROUP BY b.id""",
            (binder_id,),
        ).fetchone()
        return dict(row) if row else None

    def update(self, binder_id: int, data: Dict[str, Any]) -> bool:
        fields = []
        params = []
        allowed = ("name", "description", "color", "binder_type", "storage_location")
        for key in allowed:
            if key in data:
                fields.append(f"{key} = ?")
                params.append(data[key])
        if not fields:
            return False
        fields.append("updated_at = ?")
        params.append(now_iso())
        params.append(binder_id)
        cursor = self.conn.execute(
            f"UPDATE binders SET {', '.join(fields)} WHERE id = ?", params
        )
        return cursor.rowcount > 0

    def delete(self, binder_id: int) -> bool:
        # Log movements before clearing assignments
        rows = self.conn.execute(
            "SELECT id FROM collection WHERE binder_id = ?", (binder_id,)
        ).fetchall()
        for row in rows:
            _log_movement(self.conn, row["id"], None, None,
                          binder_id, None, None, None, note="binder deleted")
        self.conn.execute(
            "UPDATE collection SET binder_id = NULL WHERE binder_id = ?",
            (binder_id,),
        )
        cursor = self.conn.execute("DELETE FROM binders WHERE id = ?", (binder_id,))
        return cursor.rowcount > 0

    def list_all(self) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            """SELECT b.*,
                      COUNT(c.id) as card_count,
                      COALESCE(SUM(c.purchase_price), 0) as total_value
               FROM binders b
               LEFT JOIN collection c ON c.binder_id = b.id
               GROUP BY b.id
               ORDER BY b.name"""
        )
        return [dict(row) for row in cursor]

    def get_cards(self, binder_id: int) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            """SELECT c.id, c.printing_id, c.finish, c.condition, c.language,
                      c.purchase_price, c.acquired_at,
                      p.set_code, p.collector_number, p.rarity, p.artist,
                      p.image_uri, p.frame_effects, p.border_color, p.full_art,
                      p.promo, p.promo_types, p.finishes,
                      card.name, card.type_line, card.mana_cost, card.cmc,
                      card.colors, card.color_identity, p.oracle_id,
                      s.set_name
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               JOIN cards card ON p.oracle_id = card.oracle_id
               JOIN sets s ON p.set_code = s.set_code
               WHERE c.binder_id = ?
               ORDER BY card.name""",
            (binder_id,),
        )
        return [dict(row) for row in cursor]

    def add_cards(self, binder_id: int, collection_ids: List[int]) -> int:
        if not collection_ids:
            return 0
        placeholders = ",".join("?" * len(collection_ids))
        # Check for deck conflicts (only block cards in constructed decks)
        deck_conflicts = self.conn.execute(
            f"SELECT dc.collection_id FROM deck_cards dc "
            f"JOIN decks d ON dc.deck_id = d.id "
            f"WHERE dc.collection_id IN ({placeholders}) "
            f"AND d.state_id = {DECK_STATE_CONSTRUCTED}",
            collection_ids,
        ).fetchall()
        # Check for binder conflicts
        binder_conflicts = self.conn.execute(
            f"SELECT id FROM collection "
            f"WHERE id IN ({placeholders}) AND binder_id IS NOT NULL",
            collection_ids,
        ).fetchall()
        conflict_ids = [r["collection_id"] for r in deck_conflicts] + [r["id"] for r in binder_conflicts]
        if conflict_ids:
            raise ValueError(f"Cards already assigned to a deck or binder: {conflict_ids}")
        cursor = self.conn.execute(
            f"UPDATE collection SET binder_id = ? WHERE id IN ({placeholders})",
            [binder_id] + collection_ids,
        )
        for cid in collection_ids:
            _log_movement(self.conn, cid, None, None, None, binder_id, None, None)
        return cursor.rowcount

    def remove_cards(self, binder_id: int, collection_ids: List[int]) -> int:
        if not collection_ids:
            return 0
        placeholders = ",".join("?" * len(collection_ids))
        cursor = self.conn.execute(
            f"UPDATE collection SET binder_id = NULL "
            f"WHERE binder_id = ? AND id IN ({placeholders})",
            [binder_id] + collection_ids,
        )
        for cid in collection_ids:
            _log_movement(self.conn, cid, None, None, binder_id, None, None, None)
        return cursor.rowcount

    def move_cards(self, collection_ids: List[int], target_binder_id: int) -> int:
        if not collection_ids:
            return 0
        placeholders = ",".join("?" * len(collection_ids))
        # Read current state before moving
        rows = self.conn.execute(
            f"SELECT c.id, dc.deck_id, c.binder_id, dc.zone AS deck_zone "
            f"FROM collection c "
            f"LEFT JOIN deck_cards dc ON dc.collection_id = c.id "
            f"WHERE c.id IN ({placeholders})",
            collection_ids,
        ).fetchall()
        # Remove from any deck
        self.conn.execute(
            f"DELETE FROM deck_cards WHERE collection_id IN ({placeholders})",
            collection_ids,
        )
        # Assign to binder
        cursor = self.conn.execute(
            f"UPDATE collection SET binder_id = ? WHERE id IN ({placeholders})",
            [target_binder_id] + collection_ids,
        )
        for row in rows:
            _log_movement(self.conn, row["id"], row["deck_id"], None,
                          row["binder_id"], target_binder_id, row["deck_zone"], None)
        return cursor.rowcount


class CollectionViewRepository:
    """CRUD operations for collection_views table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, view: CollectionView) -> int:
        ts = now_iso()
        cursor = self.conn.execute(
            """INSERT INTO collection_views (name, description, filters_json,
               created_at, updated_at) VALUES (?, ?, ?, ?, ?)""",
            (view.name, view.description, view.filters_json, ts, ts),
        )
        return cursor.lastrowid

    def get(self, view_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM collection_views WHERE id = ?", (view_id,)
        ).fetchone()
        return dict(row) if row else None

    def update(self, view_id: int, data: Dict[str, Any]) -> bool:
        fields = []
        params = []
        allowed = ("name", "description", "filters_json")
        for key in allowed:
            if key in data:
                fields.append(f"{key} = ?")
                params.append(data[key])
        if not fields:
            return False
        fields.append("updated_at = ?")
        params.append(now_iso())
        params.append(view_id)
        cursor = self.conn.execute(
            f"UPDATE collection_views SET {', '.join(fields)} WHERE id = ?", params
        )
        return cursor.rowcount > 0

    def delete(self, view_id: int) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM collection_views WHERE id = ?", (view_id,)
        )
        return cursor.rowcount > 0

    def list_all(self) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM collection_views ORDER BY name"
        )
        return [dict(row) for row in cursor]


class BatchRepository:
    """CRUD operations for batches table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, batch: "Batch") -> int:
        ts = now_iso()
        cursor = self.conn.execute(
            """INSERT INTO batches (batch_uuid, name, deck_id, deck_zone,
               card_count, batch_type, product_type, set_code, notes, order_id,
               created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (batch.batch_uuid, batch.name, batch.deck_id, batch.deck_zone,
             batch.card_count, batch.batch_type, batch.product_type,
             batch.set_code, batch.notes, batch.order_id, ts),
        )
        return cursor.lastrowid

    def get(self, batch_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_uuid(self, batch_uuid: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM batches WHERE batch_uuid = ?", (batch_uuid,)
        ).fetchone()
        return dict(row) if row else None

    def list_all(self, batch_type: Optional[str] = None) -> List[Dict[str, Any]]:
        # Order batches are represented as a peer top-level resource at
        # /orders, so they're excluded from the generic batches list. If a
        # caller explicitly asks for batch_type='order' we still honor it.
        if batch_type:
            cursor = self.conn.execute(
                """SELECT b.*, d.name as deck_name,
                          o.order_number, o.seller_name, o.total as order_total
                   FROM batches b
                   LEFT JOIN decks d ON b.deck_id = d.id
                   LEFT JOIN orders o ON b.order_id = o.id
                   WHERE b.batch_type = ?
                   ORDER BY b.created_at DESC""",
                (batch_type,),
            )
        else:
            cursor = self.conn.execute(
                """SELECT b.*, d.name as deck_name,
                          o.order_number, o.seller_name, o.total as order_total
                   FROM batches b
                   LEFT JOIN decks d ON b.deck_id = d.id
                   LEFT JOIN orders o ON b.order_id = o.id
                   WHERE b.batch_type != 'order'
                   ORDER BY b.created_at DESC"""
            )
        return [dict(row) for row in cursor]

    def get_cards(self, batch_id: int) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            """SELECT c.id, c.printing_id, c.finish, c.condition,
                      p.set_code, p.collector_number, p.rarity, p.image_uri,
                      card.name, card.type_line, card.mana_cost,
                      s.set_name
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               JOIN cards card ON p.oracle_id = card.oracle_id
               JOIN sets s ON p.set_code = s.set_code
               WHERE c.batch_id = ?
               ORDER BY card.name""",
            (batch_id,),
        )
        return [dict(row) for row in cursor]

    def update(self, batch_id: int, **kwargs) -> bool:
        """Update batch metadata. Accepts name, product_type, set_code, notes."""
        allowed = {"name", "product_type", "set_code", "notes"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [batch_id]
        cursor = self.conn.execute(
            f"UPDATE batches SET {set_clause} WHERE id = ?", values
        )
        return cursor.rowcount > 0

    def increment_card_count(self, batch_id: int, count: int = 1) -> None:
        self.conn.execute(
            "UPDATE batches SET card_count = card_count + ? WHERE id = ?",
            (count, batch_id),
        )

    def set_deck(self, batch_id: int, deck_id: int, deck_zone: str = "mainboard") -> None:
        self.conn.execute(
            "UPDATE batches SET deck_id = ?, deck_zone = ? WHERE id = ?",
            (deck_id, deck_zone, batch_id),
        )

    def complete(self, batch_id: int) -> None:
        self.conn.execute(
            "UPDATE batches SET completed_at = ? WHERE id = ?",
            (now_iso(), batch_id),
        )


# Backward-compatible alias
CornerBatchRepository = BatchRepository
