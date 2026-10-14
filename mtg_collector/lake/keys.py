"""Whether a tenant's lake key may be derived (lakehouse K7).

The state lives in `registry.sqlite` (`lake_tenant_key`); the key does not live
anywhere.  `lake_key` is the only door to a key and it looks at the state BEFORE
it looks at the master key file, so a tombstoned tenant is refused whether or
not the master is present, and a missing master can never be mistaken for a
deletion: the two are different exception types, and
`LakeKeyError.deliberate_revocation` is true of exactly one of them.

Absence is not permission.  An id with no row is refused, so a registry that
came back empty from a restore is loud rather than permissive.

Backup and destruction are different acts on different objects: the master key
file is backed up by hand (deploy/LAKE-KEYS.md) and this module never copies
it; a tombstone is a row and never touches the file.  Nothing here reads
the BYO Anthropic key's table or master.
"""

from mtg_collector.lake import crypto
from mtg_collector.utils import now_iso


class LakeKeyError(Exception):
    deliberate_revocation = False


class KeyTombstoned(LakeKeyError):
    """The tenant's key was revoked on purpose.  The only deliberate refusal."""

    deliberate_revocation = True


class KeyUnregistered(LakeKeyError):
    """No state row: refused, because an empty registry must not be permissive."""


def state(conn, database_id: str):
    row = conn.execute(
        "SELECT state FROM lake_tenant_key WHERE database_id = ?", (database_id,)
    ).fetchone()
    return row[0] if row else None


def register(conn, database_id: str) -> None:
    """Make a tenant's key derivable.  Idempotent; refuses a tombstoned id."""
    current = state(conn, database_id)
    if current == "tombstoned":
        raise KeyTombstoned(f"{database_id} is tombstoned; a tombstone is terminal")
    if current is None:
        conn.execute(
            "INSERT INTO lake_tenant_key (database_id, state, registered_at) "
            "VALUES (?, 'active', ?)", (database_id, now_iso()),
        )


def tombstone_in_tx(conn, database_id: str, reason: str) -> None:
    """Revoke, inside the caller's transaction.  Records an id that was never
    registered too: revoking must not depend on having been registered."""
    current = state(conn, database_id)
    if current == "tombstoned":
        return
    now = now_iso()
    if current is None:
        conn.execute(
            "INSERT INTO lake_tenant_key (database_id, state, registered_at, tombstoned_at, reason) "
            "VALUES (?, 'tombstoned', ?, ?, ?)", (database_id, now, now, reason),
        )
    else:
        conn.execute(
            "UPDATE lake_tenant_key SET state = 'tombstoned', tombstoned_at = ?, reason = ? "
            "WHERE database_id = ?", (now, reason, database_id),
        )


def tombstone(conn, database_id: str, reason: str) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        tombstone_in_tx(conn, database_id, reason)
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def lake_key(conn, database_id: str, master: bytes) -> bytes:
    """The tenant's key, or the reason it is refused."""
    current = state(conn, database_id)
    if current is None:
        raise KeyUnregistered(f"{database_id} has no lake key state; register it first")
    if current == "tombstoned":
        raise KeyTombstoned(f"{database_id} was tombstoned; its key is never derived again")
    return crypto.derive_key(master, database_id)
