"""Whose Anthropic key an OCR job runs on.

Single-tenant mode (tenant_id None) uses ANTHROPIC_API_KEY, as it always has.
Multi mode uses only the requesting tenant's key from the registry, and the
environment key is never consulted: a tenant with no key has photo ingest
disabled, it does not borrow the host's.
"""

import os
from typing import Optional

from mtg_collector.tenancy import paths

NO_KEY_MESSAGE = (
    "No Anthropic API key is set for this account — photo ingest is disabled. "
    "Ask the host to run `mtg tenant set-key <handle>`."
)


def tenant_api_key(tenant_id: Optional[str]) -> Optional[str]:
    if tenant_id is None:
        return os.environ.get("ANTHROPIC_API_KEY") or None
    paths.validate_database_id(tenant_id)
    from mtg_collector.db import registry

    conn = registry.open_registry(create=False)
    try:
        return registry.get_tenant_key(conn, tenant_id)
    finally:
        conn.close()


def has_tenant_api_key(tenant_id: Optional[str]) -> bool:
    return tenant_api_key(tenant_id) is not None
