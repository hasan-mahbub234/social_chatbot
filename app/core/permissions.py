"""Role-based access control and permissions."""
from enum import Enum
from typing import List
from fastapi import HTTPException, status


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(str, Enum):
    # Agent permissions
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    # Conversation permissions
    CONVERSATION_CREATE = "conversation:create"
    CONVERSATION_READ = "conversation:read"
    CONVERSATION_DELETE = "conversation:delete"
    # Organization permissions
    ORG_MANAGE = "org:manage"
    ORG_INVITE = "org:invite"
    # Admin permissions
    ADMIN_ACCESS = "admin:access"
    USAGE_VIEW = "usage:view"


ROLE_PERMISSIONS: dict[Role, List[Permission]] = {
    Role.OWNER: list(Permission),
    Role.ADMIN: [
        Permission.AGENT_CREATE, Permission.AGENT_READ,
        Permission.AGENT_UPDATE, Permission.AGENT_DELETE,
        Permission.CONVERSATION_CREATE, Permission.CONVERSATION_READ,
        Permission.CONVERSATION_DELETE, Permission.ORG_INVITE,
        Permission.USAGE_VIEW,
    ],
    Role.MEMBER: [
        Permission.AGENT_READ, Permission.CONVERSATION_CREATE,
        Permission.CONVERSATION_READ, Permission.CONVERSATION_DELETE,
    ],
    Role.VIEWER: [
        Permission.AGENT_READ, Permission.CONVERSATION_READ,
    ],
}


def has_permission(role: str, permission: Permission) -> bool:
    """Check if role has a specific permission."""
    try:
        r = Role(role)
        return permission in ROLE_PERMISSIONS.get(r, [])
    except ValueError:
        return False


def require_permission(role: str, permission: Permission):
    """Raise 403 if role lacks permission."""
    if not has_permission(role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission}",
        )
