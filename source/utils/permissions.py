"""
Permission system for role-based access control
"""

from functools import wraps
from typing import List, Callable
from fastapi import HTTPException, status

from db.models.user import User
from db.models.enums import RoleEnum


class PermissionDenied(HTTPException):
    """Exception raised when user lacks required permissions"""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message
        )


def require_permissions(*required_permissions: str):
    """
    Decorator for endpoints requiring specific permissions

    Usage:
        @router.get("/leads")
        @require_permissions("leads.read")
        async def get_leads(user: User = Depends(User.current)):
            ...

        @router.post("/leads")
        @require_permissions("leads.write", "leads.create")
        async def create_lead(user: User = Depends(User.current)):
            ...

    Args:
        *required_permissions: Permission strings (e.g., "leads.read", "leads.write")

    Raises:
        PermissionDenied: If user lacks any required permission
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user from kwargs (injected by User.current() dependency)
            user: User = kwargs.get('user')

            if not user:
                raise PermissionDenied("Authentication required")

            # Owners have all permissions
            if user.role == RoleEnum.OWNER:
                return await func(*args, **kwargs)

            # Check if user has all required permissions
            user_permissions = set(user.permissions or [])

            missing_permissions = [
                perm for perm in required_permissions
                if perm not in user_permissions
            ]

            if missing_permissions:
                raise PermissionDenied(
                    f"Missing permissions: {', '.join(missing_permissions)}"
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_role(*allowed_roles: RoleEnum):
    """
    Decorator for endpoints requiring specific roles

    Usage:
        @router.post("/users")
        @require_role(RoleEnum.OWNER, RoleEnum.COMPANY_ADMIN)
        async def create_user(user: User = Depends(User.current)):
            ...

    Args:
        *allowed_roles: Allowed role enums

    Raises:
        PermissionDenied: If user role not in allowed_roles
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user: User = kwargs.get('user')

            if not user:
                raise PermissionDenied("Authentication required")

            if user.role not in allowed_roles:
                raise PermissionDenied(
                    f"Role '{user.role.value}' is not allowed. "
                    f"Required: {[r.value for r in allowed_roles]}"
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


class Permissions:
    """
    Permission constants for the platform

    Organized by resource type
    """

    # Leads
    LEADS_READ = "leads.read"
    LEADS_WRITE = "leads.write"
    LEADS_DELETE = "leads.delete"
    LEADS_ASSIGN = "leads.assign"

    # Contacts
    CONTACTS_READ = "contacts.read"
    CONTACTS_WRITE = "contacts.write"
    CONTACTS_DELETE = "contacts.delete"
    CONTACTS_IMPORT = "contacts.import"
    CONTACTS_EXPORT = "contacts.export"

    # Deals
    DEALS_READ = "deals.read"
    DEALS_WRITE = "deals.write"
    DEALS_DELETE = "deals.delete"
    DEALS_ASSIGN = "deals.assign"

    # Tasks
    TASKS_READ = "tasks.read"
    TASKS_WRITE = "tasks.write"
    TASKS_DELETE = "tasks.delete"
    TASKS_ASSIGN = "tasks.assign"

    # Calls
    CALLS_READ = "calls.read"
    CALLS_WRITE = "calls.write"
    CALLS_MAKE = "calls.make"

    # Notes
    NOTES_READ = "notes.read"
    NOTES_WRITE = "notes.write"
    NOTES_DELETE = "notes.delete"

    # Users
    USERS_READ = "users.read"
    USERS_CREATE = "users.create"
    USERS_UPDATE = "users.update"
    USERS_WRITE = "users.write"
    USERS_DELETE = "users.delete"
    USERS_MANAGE = "users.manage"

    # Statistics
    STATS_READ = "stats.read"
    STATS_EXPORT = "stats.export"

    # Settings
    SETTINGS_READ = "settings.read"
    SETTINGS_MANAGE = "settings.manage"

    # Company
    COMPANY_READ = "company.read"
    COMPANY_MANAGE = "company.manage"
    COMPANY_DELETE = "company.delete"


# Role-Permission mapping
ROLE_PERMISSIONS = {
    RoleEnum.OWNER: [
        # Owners have all permissions
        "*"
    ],
    RoleEnum.COMPANY_ADMIN: [
        # Leads
        Permissions.LEADS_READ,
        Permissions.LEADS_WRITE,
        Permissions.LEADS_DELETE,
        Permissions.LEADS_ASSIGN,
        # Contacts
        Permissions.CONTACTS_READ,
        Permissions.CONTACTS_WRITE,
        Permissions.CONTACTS_DELETE,
        Permissions.CONTACTS_IMPORT,
        Permissions.CONTACTS_EXPORT,
        # Deals
        Permissions.DEALS_READ,
        Permissions.DEALS_WRITE,
        Permissions.DEALS_DELETE,
        Permissions.DEALS_ASSIGN,
        # Tasks
        Permissions.TASKS_READ,
        Permissions.TASKS_WRITE,
        Permissions.TASKS_DELETE,
        Permissions.TASKS_ASSIGN,
        # Calls
        Permissions.CALLS_READ,
        Permissions.CALLS_WRITE,
        Permissions.CALLS_MAKE,
        # Notes
        Permissions.NOTES_READ,
        Permissions.NOTES_WRITE,
        Permissions.NOTES_DELETE,
        # Users
        Permissions.USERS_READ,
        Permissions.USERS_CREATE,
        Permissions.USERS_UPDATE,
        Permissions.USERS_WRITE,
        Permissions.USERS_DELETE,
        Permissions.USERS_MANAGE,
        # Statistics
        Permissions.STATS_READ,
        Permissions.STATS_EXPORT,
        # Settings
        Permissions.SETTINGS_READ,
        Permissions.SETTINGS_MANAGE,
        # Company
        Permissions.COMPANY_READ,
        Permissions.COMPANY_MANAGE,
    ],
    RoleEnum.COMPANY_MANAGER: [
        # Leads
        Permissions.LEADS_READ,
        Permissions.LEADS_WRITE,
        Permissions.LEADS_ASSIGN,
        # Contacts
        Permissions.CONTACTS_READ,
        Permissions.CONTACTS_WRITE,
        Permissions.CONTACTS_IMPORT,
        Permissions.CONTACTS_EXPORT,
        # Deals
        Permissions.DEALS_READ,
        Permissions.DEALS_WRITE,
        Permissions.DEALS_ASSIGN,
        # Tasks
        Permissions.TASKS_READ,
        Permissions.TASKS_WRITE,
        Permissions.TASKS_ASSIGN,
        # Calls
        Permissions.CALLS_READ,
        Permissions.CALLS_WRITE,
        Permissions.CALLS_MAKE,
        # Notes
        Permissions.NOTES_READ,
        Permissions.NOTES_WRITE,
        # Users
        Permissions.USERS_READ,
        # Statistics
        Permissions.STATS_READ,
        # Settings
        Permissions.SETTINGS_READ,
        # Company
        Permissions.COMPANY_READ,
    ],
    RoleEnum.COMPANY_OPERATOR: [
        # Leads
        Permissions.LEADS_READ,
        # Contacts
        Permissions.CONTACTS_READ,
        # Deals
        Permissions.DEALS_READ,
        # Tasks
        Permissions.TASKS_READ,
        Permissions.TASKS_WRITE,  # Can manage own tasks
        # Calls
        Permissions.CALLS_READ,
        Permissions.CALLS_WRITE,
        Permissions.CALLS_MAKE,
        # Notes
        Permissions.NOTES_READ,
        Permissions.NOTES_WRITE,  # Can add notes
        # Company
        Permissions.COMPANY_READ,
    ],
}


def get_permissions_for_role(role: RoleEnum) -> List[str]:
    """
    Get list of permissions for a role

    Args:
        role: User role

    Returns:
        List of permission strings
    """
    if role == RoleEnum.OWNER:
        # Return all permissions
        return ["*"]

    return ROLE_PERMISSIONS.get(role, [])


def check_permission(user: User, permission: str) -> bool:
    """
    Check if user has a specific permission

    Args:
        user: User object
        permission: Permission string

    Returns:
        True if user has permission
    """
    if user.role == RoleEnum.OWNER:
        return True

    return permission in (user.permissions or [])
