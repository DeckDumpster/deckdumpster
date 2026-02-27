"""Order resolution: match parsed order items to local DB cards."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from mtg_collector.db.models import CollectionEntry, Order
from mtg_collector.services.order_parser import ParsedOrder, ParsedOrderItem
from mtg_collector.utils import normalize_condition, normalize_finish, now_iso

# Vendor set name → DB set code
# Covers common TCGPlayer set names that don't directly match DB codes
SET_NAME_MAP = {
    "FINAL FANTASY": "fin",
    "FINAL FANTASY VARIANTS": "fin",
    "FINAL FANTASY: THROUGH THE AGES": "fca",
}

# Set hints that indicate non-MTG products — skip resolution entirely
NON_MTG_PREFIXES = ("SV", "ME:", "INTO THE INKLANDS")


@dataclass
class ResolvedItem:
    """A parsed order item matched to a local DB card."""
    parsed: ParsedOrderItem
    printing_id: Optional[str] = None
    card_name: Optional[str] = None  # resolved name from DB
    set_code: Optional[str] = None
    collector_number: Optional[str] = None
    image_uri: Optional[str] = None
    error: Optional[str] = None
    linked_collection_id: Optional[int] = None  # if matched to existing entry


@dataclass
class ResolvedOrder:
    """A parsed order with all items resolved."""
    parsed: ParsedOrder
    items: List[ResolvedItem] = field(default_factory=list)


def resolve_orders(
    orders: List[ParsedOrder],
    card_repo,
    set_repo,
    printing_repo,
) -> List[ResolvedOrder]:
    """Resolve parsed orders by matching items to cards in the local DB."""
    resolved = []
    for order in orders:
        resolved_order = ResolvedOrder(parsed=order)
        for item in order.items:
            resolved_item = _resolve_item(
                item, card_repo, set_repo, printing_repo
            )
            resolved_order.items.append(resolved_item)
        resolved.append(resolved_order)
    return resolved


def _resolve_set_code(set_hint: Optional[str], set_repo) -> Optional[str]:
    """Map a vendor set name to a set code using local DB."""
    if not set_hint:
        return None

    # Check hardcoded map first
    if set_hint.upper() in SET_NAME_MAP:
        return SET_NAME_MAP[set_hint.upper()]

    # Try local DB — check if it's already a valid set code
    s = set_repo.get(set_hint.lower())
    if s:
        return s.set_code

    # Try local DB — search by set name
    s = set_repo.get_by_name(set_hint)
    if s:
        return s.set_code

    return None


def _is_non_mtg(set_hint: Optional[str]) -> bool:
    """Check if a set hint indicates a non-MTG product (Pokemon, Lorcana, etc.)."""
    if not set_hint:
        return False
    upper = set_hint.upper()
    return any(upper.startswith(prefix) for prefix in NON_MTG_PREFIXES)


def _printing_matches_treatment(p, treatment: Optional[str]) -> bool:
    """Check if a printing matches the expected treatment (borderless, extended art, etc.)."""
    fe = p.frame_effects if isinstance(p.frame_effects, list) else []
    if isinstance(p.frame_effects, str):
        import json
        try:
            fe = json.loads(p.frame_effects)
        except (json.JSONDecodeError, TypeError):
            fe = []

    if treatment:
        t = treatment.lower()
        if "borderless" in t:
            return p.border_color == "borderless"
        if "extended" in t:
            return "extendedart" in fe
        if "showcase" in t:
            return "showcase" in fe
        # Unknown treatment — don't filter
        return True

    # No treatment = regular printing (black border, no borderless/extendedart)
    return p.border_color != "borderless" and "extendedart" not in fe


def _find_card_local(
    card_name: str, card_repo, printing_repo,
    set_code: Optional[str], treatment: Optional[str] = None,
) -> Optional[ResolvedItem]:
    """Try to find a card in the local DB. Returns ResolvedItem or None."""
    card = card_repo.get_by_name(card_name) or card_repo.search_by_name(card_name)
    if not card:
        return None

    printings = printing_repo.get_by_oracle_id(card.oracle_id)
    if not printings:
        return None

    def _make_result(p):
        return ResolvedItem(
            parsed=None,  # caller sets this
            printing_id=p.printing_id,
            card_name=card.name,
            set_code=p.set_code,
            collector_number=p.collector_number,
            image_uri=p.image_uri,
        )

    # If we have a set code, prefer a printing from that set + matching treatment
    if set_code:
        # Best: set + treatment match
        for p in printings:
            if p.set_code == set_code and _printing_matches_treatment(p, treatment):
                return _make_result(p)
        # Fallback: set match only
        for p in printings:
            if p.set_code == set_code:
                return _make_result(p)

    # Use any available printing
    p = printings[0]
    return _make_result(p)


def _resolve_item(
    item: ParsedOrderItem,
    card_repo,
    set_repo,
    printing_repo,
) -> ResolvedItem:
    """Resolve a single order item to a card using local DB only."""
    resolved = ResolvedItem(parsed=item)

    # Skip non-MTG products immediately
    if _is_non_mtg(item.set_hint):
        resolved.error = f"Non-MTG product: {item.card_name}"
        return resolved

    # Clean card name — remove collector number suffixes like "(0393)"
    card_name = item.card_name
    card_name = re.sub(r'\s*\(\d+\)\s*$', '', card_name)
    # Remove collector number suffixes like "- 065/182"
    card_name = re.sub(r'\s*-\s*\d+/\d+\s*$', '', card_name)
    # Remove collector number suffixes like "- 026"
    card_name = re.sub(r'\s*-\s*\d+\s*$', '', card_name)

    set_code = _resolve_set_code(item.set_hint, set_repo)

    treatment = item.treatment

    # Best path: exact set_code + collector_number lookup (e.g., from CK HTML)
    if set_code and item.collector_number:
        p = printing_repo.get_by_set_cn(set_code, item.collector_number)
        if p:
            card = card_repo.get(p.oracle_id)
            resolved.printing_id = p.printing_id
            resolved.card_name = card.name if card else card_name
            resolved.set_code = p.set_code
            resolved.collector_number = p.collector_number
            resolved.image_uri = p.image_uri
            return resolved

    # Try local DB — full name
    result = _find_card_local(card_name, card_repo, printing_repo, set_code, treatment)
    if result:
        result.parsed = item
        return result

    # For names with " - " (e.g. "FF Name - MTG Name"), try just the MTG part
    if " - " in card_name:
        mtg_name = card_name.split(" - ", 1)[1].strip()
        result = _find_card_local(mtg_name, card_repo, printing_repo, set_code, treatment)
        if result:
            result.parsed = item
            return result

    resolved.error = f"Card not found: {card_name} (run `mtg cache all` to populate)"
    return resolved


def commit_orders(
    resolved_orders: List[ResolvedOrder],
    order_repo,
    collection_repo,
    conn,
    status: str = "ordered",
    source: str = "order_import",
) -> Dict:
    """Commit resolved orders to the database.

    Creates order records and collection entries (or links existing ones).

    Returns summary dict with counts.
    """
    summary = {
        "orders_created": 0,
        "orders_skipped": 0,
        "cards_added": 0,
        "cards_linked": 0,
        "cards_skipped": 0,
        "errors": [],
    }

    ts = now_iso()

    for resolved in resolved_orders:
        parsed = resolved.parsed

        # Idempotency: skip if order_number + seller already exists
        existing_orders = order_repo.get_by_number(parsed.order_number)
        already_exists = any(
            o.seller_name == parsed.seller_name for o in existing_orders
        )
        if already_exists:
            summary["orders_skipped"] += 1
            continue

        # Create order record
        order = Order(
            id=None,
            order_number=parsed.order_number,
            source=parsed.source,
            seller_name=parsed.seller_name,
            order_date=parsed.order_date,
            subtotal=parsed.subtotal,
            shipping=parsed.shipping,
            tax=parsed.tax,
            total=parsed.total,
            shipping_status=parsed.shipping_status,
            estimated_delivery=parsed.estimated_delivery,
            created_at=ts,
        )
        order_id = order_repo.add(order)
        summary["orders_created"] += 1

        for item in resolved.items:
            if not item.printing_id:
                summary["errors"].append(item.error or f"Unresolved: {item.parsed.card_name}")
                continue

            for _ in range(item.parsed.quantity):
                # Check for existing unlinked ordered card with same printing_id
                existing = _find_existing_unlinked(
                    conn, item.printing_id, status
                )

                if existing:
                    # Link existing entry to this order
                    conn.execute(
                        "UPDATE collection SET order_id = ? WHERE id = ?",
                        (order_id, existing),
                    )
                    summary["cards_linked"] += 1
                else:
                    # Create new collection entry
                    finish = normalize_finish("foil" if item.parsed.foil else "nonfoil")
                    condition = normalize_condition(item.parsed.condition)
                    entry = CollectionEntry(
                        id=None,
                        printing_id=item.printing_id,
                        finish=finish,
                        condition=condition,
                        purchase_price=item.parsed.price,
                        source=source,
                        status=status,
                        order_id=order_id,
                        acquired_at=ts,
                    )
                    collection_repo.add(entry)
                    summary["cards_added"] += 1

    conn.commit()
    return summary


def _find_existing_unlinked(
    conn, printing_id: str, status: str
) -> Optional[int]:
    """Find an existing collection entry with matching printing_id, status, and no order_id."""
    cursor = conn.execute(
        "SELECT id FROM collection WHERE printing_id = ? AND status = ? AND order_id IS NULL LIMIT 1",
        (printing_id, status),
    )
    row = cursor.fetchone()
    return row["id"] if row else None
