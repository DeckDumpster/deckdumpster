"""Multi-tenancy: where a tenant's files live, and who the tenants are."""

from mtg_collector.tenancy.context import (
    SINGLE_TENANT,
    NoTenantError,
    SingleTenantResolver,
    TenantId,
    bind,
    current_tenant,
)

__all__ = [
    "SINGLE_TENANT",
    "NoTenantError",
    "SingleTenantResolver",
    "TenantId",
    "bind",
    "current_tenant",
]
