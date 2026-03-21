"""Database layer for MTG Collector."""

from mtg_collector.db.connection import close_connection, get_connection, get_db_path
from mtg_collector.db.models import (
    CardRepository,
    CollectionRepository,
    OrderRepository,
    PrintingRepository,
    SetRepository,
    WishlistRepository,
)
from mtg_collector.db.schema import (
    SCHEMA_VERSION,
    SHARED_TABLES,
    init_db,
    init_shared_db,
    init_user_db,
)

__all__ = [
    "get_db_path",
    "get_connection",
    "close_connection",
    "init_db",
    "init_shared_db",
    "init_user_db",
    "SCHEMA_VERSION",
    "SHARED_TABLES",
    "CardRepository",
    "SetRepository",
    "PrintingRepository",
    "CollectionRepository",
    "OrderRepository",
    "WishlistRepository",
]
