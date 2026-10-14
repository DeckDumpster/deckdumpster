"""Where a tenant's objects live and what a set of events means (lakehouse K7).

The one definition of the tenant-zone key layout and the one resolution rule;
the shipper, the read-back and the eraser import it, and
`tests/test_tenant_zone_governance.py` holds the prefix here equal to the one in
the policy documents and in deploy/setup-tenant-zone.sh, which cannot import it.

    tenant/database_id=<ULID>/dataset=holdings/as_of=YYYY-MM-DD/part-seq-<from>-<to>.parquet.enc

`database_id` is the first partition so that deleting a tenant is one prefix.

The resolution rule: events are `(seq, source, row_id, op, payload)`; per
(source, row_id) the event with the highest seq wins, and a winning delete
leaves nothing.  Order of arrival is irrelevant and applying a log twice
changes nothing, which is what makes delivery at-least-once safe.
"""

import json
import re

TENANT_PREFIX = "tenant/"
CATALOG_PREFIXES = ("raw/", "lake/")
RETENTION_DAYS = 90
HOLDINGS_DATASET = "holdings"

_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_AS_OF = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_id(database_id: str) -> str:
    if not _ULID.match(database_id):
        raise ValueError(f"not a database_id: {database_id!r}")
    return database_id


def tenant_prefix(database_id: str) -> str:
    """Everything of a tenant's, derived artifacts included: the unit of erasure."""
    return f"{TENANT_PREFIX}database_id={_check_id(database_id)}/"


def partition_prefix(database_id: str, dataset: str, as_of: str) -> str:
    if not _AS_OF.match(as_of):
        raise ValueError(f"not a date: {as_of!r}")
    return f"{tenant_prefix(database_id)}dataset={dataset}/as_of={as_of}/"


def range_part_key(database_id: str, as_of: str, from_seq: int, to_seq: int) -> str:
    """A holdings part is named for the outbox range it carries, so a retry
    lands on the object it is retrying rather than beside it."""
    if not 0 < from_seq <= to_seq:
        raise ValueError(f"bad outbox range {from_seq}..{to_seq}")
    return (
        f"{partition_prefix(database_id, HOLDINGS_DATASET, as_of)}"
        f"part-seq-{from_seq}-{to_seq}.parquet.enc"
    )


def database_id_of(key: str) -> str:
    """Whose object this is, read from the key and nowhere else."""
    m = re.match(rf"^{re.escape(TENANT_PREFIX)}database_id=([^/]+)/", key)
    if not m:
        raise ValueError(f"not a tenant-zone key: {key!r}")
    return _check_id(m.group(1))


def resolve(events) -> dict[str, dict[int, dict]]:
    """Reduce events to the holdings they describe: source -> row_id -> payload."""
    winners: dict[tuple[str, int], tuple[int, str, object]] = {}
    for seq, source, row_id, op, payload in events:
        if op not in ("upsert", "delete"):
            raise ValueError(f"unknown outbox op {op!r}")
        cur = winners.get((source, row_id))
        if cur is None or seq > cur[0]:
            winners[(source, row_id)] = (seq, op, payload)
    out: dict[str, dict[int, dict]] = {}
    for (source, row_id), (_, op, payload) in sorted(winners.items()):
        out.setdefault(source, {})
        if op == "upsert":
            out[source][row_id] = json.loads(payload) if isinstance(payload, str) else payload
    return out
