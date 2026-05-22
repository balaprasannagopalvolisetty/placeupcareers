"""Explicit role and permission definitions for server-side authorization."""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"


class Permission(StrEnum):
    READ_PUBLIC_DATA = "read_public_data"
    READ_OWN_DATA = "read_own_data"
    WRITE_OWN_DATA = "write_own_data"
    READ_CONTACTS = "read_contacts"
    RUN_ENRICHMENT = "run_enrichment"
    RUN_INTERNAL_JOBS = "run_internal_jobs"
    ADMINISTER_SYSTEM = "administer_system"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.GUEST: {
        Permission.READ_PUBLIC_DATA,
    },
    Role.USER: {
        Permission.READ_PUBLIC_DATA,
        Permission.READ_OWN_DATA,
        Permission.WRITE_OWN_DATA,
        Permission.READ_CONTACTS,
        Permission.RUN_ENRICHMENT,
    },
    Role.ADMIN: {
        Permission.READ_PUBLIC_DATA,
        Permission.READ_OWN_DATA,
        Permission.WRITE_OWN_DATA,
        Permission.READ_CONTACTS,
        Permission.RUN_ENRICHMENT,
        Permission.RUN_INTERNAL_JOBS,
        Permission.ADMINISTER_SYSTEM,
    },
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
