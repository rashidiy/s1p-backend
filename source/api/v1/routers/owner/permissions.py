"""
Owner endpoint to list available permissions and role defaults
"""

from fastapi import APIRouter

from db.models.owner import Owner
from db.models.enums import RoleEnum
from utils.permissions import Permissions, ROLE_PERMISSIONS

router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.get("")
async def list_permissions(
    owner: Owner = Owner.current(),
):
    """
    List all available permissions and default permissions per role

    Returns every permission constant and the default set for each company role.
    """
    all_permissions = {
        attr: getattr(Permissions, attr)
        for attr in dir(Permissions)
        if not attr.startswith("_") and isinstance(getattr(Permissions, attr), str)
    }

    role_defaults = {
        role.value: perms
        for role, perms in ROLE_PERMISSIONS.items()
        if role != RoleEnum.OWNER
    }

    return {
        "permissions": all_permissions,
        "role_defaults": role_defaults,
    }
