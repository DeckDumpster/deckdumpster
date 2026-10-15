"""The catalog-zone guard: nothing that could name a tenant may enter it.

The catalog zone (raw/ and lake/catalog/) is shared by every tenant, so a tenant
identifier there is a leak.  The guard looks at three surfaces, because a
columns-only check missed the one that mattered (K3): table **columns**, the
**URLs** the landing step fetched, and the **manifest** fields written beside
each landed object.  A fetch URL chosen from a tenant's collection reveals
holdings exactly as a column would.

`selftest()` is the positive control: it plants a violation on each surface and
raises unless the guard flags it, so a guard that passes everything cannot pass.
"""

import re

TENANT_COLUMN_NAMES = frozenset({
    "tenant", "tenant_id", "tenant_key", "user", "user_id", "owner", "owner_id",
    "database_id", "collection_id", "deck_id", "binder_id", "order_id",
    "lake_tenant_key", "session_id",
})
_TENANT_TOKEN = re.compile(r"tenant|database_id|user_id|owner", re.I)
_ULID = re.compile(r"(?<![0-9A-Za-z])[0-7][0-9A-HJKMNP-TV-Z]{25}(?![0-9A-Za-z])")
# A landing run id is a ULID too, but it names a fetch, not a tenant: it is in every
# partition path (`run=<ULID>`) and in the manifest's own run_id.
_RUN_ID = re.compile(r"run=[0-7][0-9A-HJKMNP-TV-Z]{25}")


class ZoneViolation(Exception):
    pass


def check_columns(tables: dict[str, list[str]]) -> list[str]:
    return [
        f"column {t}.{c}"
        for t, cols in sorted(tables.items())
        for c in cols
        if c.lower() in TENANT_COLUMN_NAMES or _TENANT_TOKEN.search(c)
    ]


def check_urls(urls: list[str], allowed: set[str] | None = None) -> list[str]:
    """Flag tenant-shaped URLs, and, given the catalog-derived `allowed` set,
    any URL outside it."""
    bad = []
    for u in urls:
        if _TENANT_TOKEN.search(u) or _ULID.search(u):
            bad.append(f"url {u}")
        elif allowed is not None and u not in allowed:
            bad.append(f"url {u} (not in the catalog-derived fetch set)")
    return bad


def check_manifest(manifest: dict, path: str = "") -> list[str]:
    """Flag tenant-shaped keys anywhere in a manifest, and tenant-shaped values."""
    bad = []
    for k, v in manifest.items():
        here = f"{path}.{k}" if path else k
        if k.lower() in TENANT_COLUMN_NAMES or _TENANT_TOKEN.search(k):
            bad.append(f"manifest field {here}")
        if k == "run_id":
            continue
        bad += _check_value(v, here)
    return bad


def _check_value(v, here: str) -> list[str]:
    if isinstance(v, dict):
        return check_manifest(v, here)
    if isinstance(v, (list, tuple)):
        return [b for i, x in enumerate(v) for b in _check_value(x, f"{here}[{i}]")]
    if isinstance(v, str):
        v = _RUN_ID.sub("run=", v)
    if isinstance(v, str) and (_TENANT_TOKEN.search(v) or _ULID.search(v)):
        return [f"manifest value {here}={v}"]
    return []


def check_zone(tables=None, urls=None, manifests=None, allowed_urls=None) -> list[str]:
    bad = check_columns(tables or {})
    bad += check_urls(urls or [], allowed_urls)
    for m in manifests or []:
        bad += check_manifest(m)
    return bad


def assert_clean(**surfaces) -> None:
    bad = check_zone(**surfaces)
    if bad:
        raise ZoneViolation("catalog zone carries tenant-shaped data: " + "; ".join(bad))


def selftest() -> None:
    clean = dict(
        tables={"prices": ["uuid", "set_code", "price_cents"]},
        urls=["https://json.edhrec.com/pages/commanders/atraxa-praetors-voice.json"],
        manifests=[{"source": "edhrec", "sha256": "ab" * 32, "run": "run-1"}],
    )
    if check_zone(**clean):
        raise AssertionError("guard self-test: a clean zone was flagged")
    plants = {
        "column": dict(clean, tables={"prices": ["uuid", "database_id"]}),
        "url": dict(clean, urls=clean["urls"] + ["https://x/01HZX3V5K8M2N4P6Q8R0S2T4V6.json"]),
        "manifest field": dict(clean, manifests=[{"source": "edhrec", "tenant": "t1"}]),
        "manifest value": dict(clean, manifests=[{"note": "owner=alice"}]),
        "off-set url": dict(clean, allowed_urls={"https://other"}),
    }
    for name, zone in plants.items():
        if not check_zone(**zone):
            raise AssertionError(f"guard self-test: planted {name} was not flagged")
