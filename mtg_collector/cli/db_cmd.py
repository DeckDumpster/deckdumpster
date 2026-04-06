"""Database management commands: mtg db init/refresh/split"""

from mtg_collector.db import SCHEMA_VERSION, get_connection, init_db


def register(subparsers):
    """Register the db subcommand."""
    db_parser = subparsers.add_parser("db", help="Database management commands")
    db_subparsers = db_parser.add_subparsers(dest="db_command", metavar="<subcommand>")

    # db init
    init_parser = db_subparsers.add_parser("init", help="Initialize or migrate database")
    init_parser.add_argument(
        "--force", action="store_true", help="Recreate tables even if they exist"
    )
    init_parser.set_defaults(func=run_init)

    # db refresh
    refresh_parser = db_subparsers.add_parser(
        "refresh", help="Re-fetch Scryfall data for cached printings"
    )
    refresh_parser.add_argument(
        "--all", action="store_true", help="Refresh all printings (default: only stale)"
    )
    refresh_parser.set_defaults(func=run_refresh)

    # db recache
    recache_parser = db_subparsers.add_parser(
        "recache", help="Fix non-English printings and clear set cache"
    )
    recache_parser.set_defaults(func=run_recache)

    # db split
    split_parser = db_subparsers.add_parser(
        "split", help="Split monolithic DB into shared reference + user DBs"
    )
    split_parser.add_argument(
        "--shared-out", default=None,
        help="Path for shared reference DB (default: <db_dir>/shared.sqlite)",
    )
    split_parser.add_argument(
        "--prune", action="store_true",
        help="Remove shared table data from the source DB after copying",
    )
    split_parser.set_defaults(func=run_split)

    db_parser.set_defaults(func=lambda args: db_parser.print_help())


def run_init(args):
    """Initialize the database."""
    conn = get_connection(args.db_path)

    created = init_db(conn, force=args.force)

    if created:
        print(f"Database initialized at: {args.db_path}")
        print(f"Schema version: {SCHEMA_VERSION}")
    else:
        print(f"Database already up to date (version {SCHEMA_VERSION})")
        print(f"Location: {args.db_path}")


def run_split(args):
    """Split a monolithic DB into shared reference + user DBs."""
    import sqlite3
    from pathlib import Path

    from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS

    source_path = args.db_path
    shared_path = args.shared_out
    if not shared_path:
        shared_path = str(Path(source_path).parent / "shared.sqlite")

    print(f"Source DB:  {source_path}")
    print(f"Shared DB:  {shared_path}")

    # Open source and create shared DB via ATTACH
    conn = sqlite3.connect(source_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")

    # Create the shared DB with full schema
    shared_conn = sqlite3.connect(shared_path)
    shared_conn.row_factory = sqlite3.Row
    init_db(shared_conn)
    shared_conn.close()

    conn.execute("ATTACH DATABASE ? AS shared", (shared_path,))

    total_rows = 0
    for table in SHARED_TABLES:
        # Check if table exists in source
        exists = conn.execute(
            "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            continue
        conn.execute(f"DELETE FROM shared.[{table}]")
        conn.execute(f"INSERT INTO shared.[{table}] SELECT * FROM main.[{table}]")
        count = conn.execute(f"SELECT COUNT(*) FROM shared.[{table}]").fetchone()[0]
        if count:
            print(f"  {table}: {count} rows")
        total_rows += count

    conn.commit()

    # Refresh materialized price views in shared DB
    for view in SHARED_VIEWS:
        exists = conn.execute(
            "SELECT 1 FROM shared.sqlite_master WHERE type='table' AND name=?",
            (view,),
        ).fetchone()
        if exists:
            source_count = conn.execute(f"SELECT COUNT(*) FROM main.[{view}]").fetchone()[0]
            if source_count:
                conn.execute(f"DELETE FROM shared.[{view}]")
                conn.execute(f"INSERT INTO shared.[{view}] SELECT * FROM main.[{view}]")
                count = conn.execute(f"SELECT COUNT(*) FROM shared.[{view}]").fetchone()[0]
                print(f"  {view}: {count} rows")
                total_rows += count

    conn.commit()
    print(f"\nCopied {total_rows} total rows to shared DB")

    if args.prune:
        print("\nPruning shared data from source DB...")
        pruned = 0
        for table in SHARED_TABLES:
            exists = conn.execute(
                "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            count = conn.execute(f"SELECT COUNT(*) FROM main.[{table}]").fetchone()[0]
            if count:
                conn.execute(f"DELETE FROM main.[{table}]")
                print(f"  {table}: {count} rows removed")
                pruned += count
        for view in SHARED_VIEWS:
            exists = conn.execute(
                "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?",
                (view,),
            ).fetchone()
            if exists:
                count = conn.execute(f"SELECT COUNT(*) FROM main.[{view}]").fetchone()[0]
                if count:
                    conn.execute(f"DELETE FROM main.[{view}]")
                    print(f"  {view}: {count} rows removed")
                    pruned += count
        conn.commit()
        conn.execute("VACUUM main")
        print(f"Pruned {pruned} rows from source DB")

    conn.execute("DETACH DATABASE shared")
    conn.close()
    print("Done!")


def run_recache(args):
    """Fix non-English printings in collection and clear set cache."""
    import json

    from mtg_collector.db import (
        CardRepository,
        PrintingRepository,
        SetRepository,
        get_connection,
        init_db,
    )
    from mtg_collector.services.scryfall import ScryfallAPI, cache_scryfall_data

    conn = get_connection(args.db_path)
    init_db(conn)
    api = ScryfallAPI()
    card_repo = CardRepository(conn)
    set_repo = SetRepository(conn)
    printing_repo = PrintingRepository(conn)

    # Step 1: Find non-English printings referenced by collection
    cursor = conn.execute("""
        SELECT DISTINCT p.printing_id, p.set_code, p.collector_number, p.raw_json
        FROM collection c
        JOIN printings p ON c.printing_id = p.printing_id
        WHERE p.raw_json IS NOT NULL
          AND json_extract(p.raw_json, '$.lang') != 'en'
    """)
    non_english = cursor.fetchall()

    if non_english:
        print(f"Found {len(non_english)} non-English printing(s) in collection. Fixing...")
        conn.execute("PRAGMA foreign_keys = OFF")
        fixed = 0
        for row in non_english:
            old_id = row["printing_id"]
            set_code = row["set_code"]
            cn = row["collector_number"]
            old_lang = json.loads(row["raw_json"]).get("lang", "?")
            old_name = json.loads(row["raw_json"]).get("name", "?")

            # Fetch English version via /cards/{set}/{cn} (returns English by default)
            en_data = api.get_card_by_set_cn(set_code, cn)
            if not en_data:
                print(f"  SKIP: {old_name} ({set_code.upper()} #{cn}) — English version not found")
                continue

            new_id = en_data["id"]
            if new_id == old_id:
                # Already English despite raw_json saying otherwise — skip
                continue

            # Delete the old non-English printing first (unique constraint on set_code+cn)
            conn.execute("DELETE FROM printings WHERE printing_id = ?", (old_id,))

            # Cache the English printing
            cache_scryfall_data(api, card_repo, set_repo, printing_repo, en_data)

            # Update collection entries to point to English printing
            conn.execute(
                "UPDATE collection SET printing_id = ? WHERE printing_id = ?",
                (new_id, old_id),
            )

            print(f"  Fixed: {old_name} ({set_code.upper()} #{cn}) [{old_lang} -> en]")
            fixed += 1

        conn.execute("PRAGMA foreign_keys = ON")
        print(f"Fixed {fixed} printing(s)")
    else:
        print("No non-English printings found in collection.")

    # Step 2: Delete all printings not referenced by collection (cache cleanup)
    cursor = conn.execute("""
        DELETE FROM printings
        WHERE printing_id NOT IN (SELECT DISTINCT printing_id FROM collection)
    """)
    print(f"Cleaned {cursor.rowcount} cached printing(s) not in collection")

    # Step 3: Clear cache flags on all sets
    conn.execute("UPDATE sets SET cards_fetched_at = NULL")
    print("Cleared set cache flags (will re-cache on next use)")

    conn.commit()
    print("Done!")


def run_refresh(args):
    """Refresh Scryfall data for cached printings."""
    from mtg_collector.db import CardRepository, PrintingRepository, SetRepository, get_connection
    from mtg_collector.services.scryfall import ScryfallAPI, cache_scryfall_data

    conn = get_connection(args.db_path)
    printing_repo = PrintingRepository(conn)
    card_repo = CardRepository(conn)
    set_repo = SetRepository(conn)
    api = ScryfallAPI()

    # Get all printings
    cursor = conn.execute("SELECT printing_id FROM printings")
    printing_ids = [row[0] for row in cursor]

    if not printing_ids:
        print("No printings cached. Nothing to refresh.")
        return

    print(f"Refreshing {len(printing_ids)} printing(s)...")

    refreshed = 0
    errors = 0

    for printing_id in printing_ids:
        data = api.get_card_by_id(printing_id)
        if data:
            cache_scryfall_data(api, card_repo, set_repo, printing_repo, data)
            refreshed += 1
        else:
            print(f"  Failed to fetch: {printing_id}")
            errors += 1

    conn.commit()
    print(f"Refreshed {refreshed} printing(s), {errors} error(s)")
