from contextvars import ContextVar
from dataclasses import dataclass, field

from fastapi import HTTPException


@dataclass
class Access:
    """Effective resource grants for one request."""
    admin: bool = False
    user_id: int | None = None
    permissions: set[str] = field(default_factory=set)
    projects: set[str] = field(default_factory=set)
    servers: dict[str, int] = field(default_factory=dict)
    databases: dict[str, int] = field(default_factory=dict)

current_access: ContextVar[Access | None] = ContextVar('current_access', default=None)


def access_context() -> Access:
    """Return active grants, denying access when no request scope is set."""
    return current_access.get() or Access()


def allows(access: Access, permission: str) -> bool:
    """Check one independent capability, with administrator bypass."""
    return access.admin or permission in access.permissions


def require_permission(access: Access, permission: str) -> None:
    """Reject requests without the requested capability."""
    if not allows(access, permission):
        raise HTTPException(403, f'Permission required: {permission}')
