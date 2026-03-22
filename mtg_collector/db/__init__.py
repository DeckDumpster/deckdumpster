"""Database layer for MTG Collector."""

from mtg_collector.db.connection import attach_shared, close_connection, get_connection, get_db_path
from mtg_collector.db.models import (
    CardRepository,
    CollectionRepository,
    OrderRepository,
    PrintingRepository,
    SetRepository,
    WishlistRepository,
)
from mtg_collector.db.schema import SCHEMA_VERSION, SHARED_TABLES, SHARED_VIEWS, init_db

__all__ = [
    "get_db_path",
    "get_connection",
    "close_connection",
    "attach_shared",
    "init_db",
    "SCHEMA_VERSION",
    "SHARED_TABLES",
    "SHARED_VIEWS",
    "CardRepository",
    "SetRepository",
    "PrintingRepository",
    "CollectionRepository",
    "OrderRepository",
    "WishlistRepository",
]
