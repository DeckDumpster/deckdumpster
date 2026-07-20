"""Database layer for MTG Collector."""

from mtg_collector.db.connection import (
    attach_shared,
    close_connection,
    get_connection,
    get_db_path,
    get_shared_db_path,
    get_shared_write_path,
)
from mtg_collector.db.models import (
    CardRepository,
    CollectionRepository,
    OrderRepository,
    PrintingRepository,
    SetRepository,
    WishlistRepository,
)
from mtg_collector.db.schema import (
    SCHEMA_OBJECTS,
    SCHEMA_VERSION,
    SHARED_TABLES,
    SHARED_VIEWS,
    SchemaIntegrityError,
    init_db,
    verify_schema,
)

__all__ = [
    "get_db_path",
    "get_connection",
    "close_connection",
    "attach_shared",
    "get_shared_db_path",
    "get_shared_write_path",
    "init_db",
    "verify_schema",
    "SchemaIntegrityError",
    "SCHEMA_OBJECTS",
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
