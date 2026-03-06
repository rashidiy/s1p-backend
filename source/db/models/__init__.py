"""
Database models for S1P CRM platform
"""

# Core multi-tenant models
from .owner import Owner
from .company import Company
from .user import User

# Telephony models
from .call_event import CallEvent
from .sipuni import Sipuni  # Legacy, will be migrated to Company.provider_config

# CRM models
from .contact import Contact
from .lead import Lead
from .deal import Deal
from .task import Task
from .note import Note
from .tag import Tag

# Billing
from .contract import Contract

# Permission groups
from .permission_group import PermissionGroup

# Custom fields
from .custom_field import CustomFieldDefinition

# System models
from .audit_log import AuditLog

# Enums
from . import enums

__all__ = [
    # Core
    "Owner",
    "Company",
    "User",
    # Telephony
    "CallEvent",
    "Sipuni",  # Legacy
    # CRM
    "Contact",
    "Lead",
    "Deal",
    "Task",
    "Note",
    "Tag",
    # Billing
    "Contract",
    # Permission groups
    "PermissionGroup",
    # Custom fields
    "CustomFieldDefinition",
    # System
    "AuditLog",
    # Enums module
    "enums",
]
