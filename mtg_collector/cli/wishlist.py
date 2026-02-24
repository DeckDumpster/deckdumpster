"""Wishlist command: mtg wishlist"""

from mtg_collector.db import (
    CardRepository,
    PrintingRepository,
    WishlistRepository,
    get_connection,
    init_db,
)
from mtg_collector.utils import now_iso


def register(subparsers):
    """Register the wishlist subcommand."""
    parser = subparsers.add_parser(
        "wishlist",
        help="Manage your wishlist",
        description="Add, list, remove, and fulfill wishlist entries.",
    )
    sub = parser.add_subparsers(dest="wishlist_action", metavar="<action>")

    # wishlist add
    add_parser = sub.add_parser("add", help="Add a card to your wishlist")
    add_parser.add_argument("name", help="Card name")
    add_parser.add_argument("--set", dest="set_code", metavar="CODE", help="Preferred set code")
    add_parser.add_argument("--cn", metavar="CN", help="Collector number (requires --set)")
    add_parser.add_argument("--max-price", type=float, metavar="N", help="Maximum price willing to pay")
    add_parser.add_argument("--priority", type=int, default=0, metavar="N", help="Priority (higher = more wanted)")
    add_parser.add_argument("--notes", metavar="TEXT", help="Notes")

    # wishlist list
    list_parser = sub.add_parser("list", help="List wishlist entries")
    list_parser.add_argument("--name", metavar="NAME", help="Filter by card name")
    list_parser.add_argument("--fulfilled", action="store_true", help="Show fulfilled entries")
    list_parser.add_argument("--all", dest="show_all", action="store_true", help="Show all entries including fulfilled")
    list_parser.add_argument("--limit", type=int, metavar="N", help="Limit results")

    # wishlist remove
    remove_parser = sub.add_parser("remove", help="Remove a wishlist entry")
    remove_parser.add_argument("id", type=int, help="Wishlist entry ID")

    # wishlist fulfill
    fulfill_parser = sub.add_parser("fulfill", help="Mark a wishlist entry as fulfilled")
    fulfill_parser.add_argument("id", type=int, help="Wishlist entry ID")

    parser.set_defaults(func=run)


def run(args):
    """Run the wishlist command."""
    if not args.wishlist_action:
        print("Usage: mtg wishlist {add,list,remove,fulfill}")
        return

    conn = get_connection(args.db_path)
    init_db(conn)
    wishlist_repo = WishlistRepository(conn)

    if args.wishlist_action == "add":
        _add(args, conn, wishlist_repo)
    elif args.wishlist_action == "list":
        _list(args, wishlist_repo)
    elif args.wishlist_action == "remove":
        _remove(args, conn, wishlist_repo)
    elif args.wishlist_action == "fulfill":
        _fulfill(args, conn, wishlist_repo)


def _add(args, conn, wishlist_repo):
    """Add a card to the wishlist."""
    from mtg_collector.db.models import WishlistEntry

    card_repo = CardRepository(conn)
    printing_repo = PrintingRepository(conn)

    card = card_repo.get_by_name(args.name) or card_repo.search_by_name(args.name)
    if not card:
        print(f"No card found matching '{args.name}' (run `mtg cache all` to populate)")
        return

    oracle_id = card.oracle_id
    printing_id = None
    set_info = ""

    if args.set_code:
        # Find a specific printing in that set
        printings = printing_repo.get_by_oracle_id(oracle_id)
        set_code = args.set_code.lower()
        for p in printings:
            if p.set_code == set_code:
                if args.cn and p.collector_number != args.cn:
                    continue
                printing_id = p.printing_id
                set_info = f" ({p.set_code.upper()} #{p.collector_number})"
                break
        if not printing_id:
            print(f"No printing found for '{args.name}' in set '{args.set_code}'")
            return

    entry = WishlistEntry(
        id=None,
        oracle_id=oracle_id,
        printing_id=printing_id,
        max_price=args.max_price,
        priority=args.priority,
        notes=args.notes,
        added_at=now_iso(),
        source="manual",
    )
    new_id = wishlist_repo.add(entry)
    conn.commit()

    print(f"Added to wishlist: #{new_id} {card.name}{set_info}")


def _list(args, wishlist_repo):
    """List wishlist entries."""
    fulfilled = None
    if args.show_all:
        fulfilled = None
    elif args.fulfilled:
        fulfilled = True
    else:
        fulfilled = False

    entries = wishlist_repo.list_all(
        fulfilled=fulfilled,
        name=args.name,
        limit=args.limit,
    )

    if not entries:
        print("No wishlist entries found.")
        return

    print(f"{'ID':>6}  {'Name':<30}  {'Set':<6}  {'Pri':>3}  {'Max$':>7}  {'Status':<10}")
    print("-" * 75)

    for e in entries:
        set_code = (e["set_code"] or "any").upper()
        max_price = f"${e['max_price']:.2f}" if e["max_price"] else ""
        status = "fulfilled" if e["fulfilled_at"] else "wanted"
        print(
            f"{e['id']:>6}  "
            f"{e['name'][:30]:<30}  "
            f"{set_code[:6]:<6}  "
            f"{e['priority']:>3}  "
            f"{max_price:>7}  "
            f"{status:<10}"
        )

    print("-" * 75)
    print(f"Showing {len(entries)} entry/entries")


def _remove(args, conn, wishlist_repo):
    """Remove a wishlist entry."""
    entry = wishlist_repo.get(args.id)
    if not entry:
        print(f"No wishlist entry found with ID: {args.id}")
        return

    wishlist_repo.delete(args.id)
    conn.commit()
    print(f"Removed wishlist entry #{args.id}")


def _fulfill(args, conn, wishlist_repo):
    """Mark a wishlist entry as fulfilled."""
    entry = wishlist_repo.get(args.id)
    if not entry:
        print(f"No wishlist entry found with ID: {args.id}")
        return

    if entry.fulfilled_at:
        print(f"Wishlist entry #{args.id} is already fulfilled")
        return

    wishlist_repo.fulfill(args.id)
    conn.commit()
    print(f"Marked wishlist entry #{args.id} as fulfilled")
