# Multi-Tenant Call Center CRM Platform - Architecture Design

**Version:** 1.1
**Date:** 2026-02-17
**Status:** Post-MVP (Analytics, Contracts, Enhanced Calls implemented)
**Timeline:** Ongoing

---

## 1. EXECUTIVE SUMMARY

This document outlines the complete architecture for a multi-tenant Call Center CRM platform with telephony integrations (Sipuni and Binotel), built on FastAPI, PostgreSQL, Redis, and background job processing.

### Business Model
```
Platform (SaaS)
  └── Owners (Master Accounts)
       └── Companies (Tenants - each with one provider)
            └── Users (company_admin, company_manager, company_operator)
```

### Scale Requirements
- **1,000+** companies
- **~20** users per company
- **~150** calls/day per company
- **10,000+** calls/day platform-wide

---

## 2. MULTI-TENANCY MODEL

### Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                         PLATFORM                             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ OWNER 1 (owner@company.com)                          │  │
│  │                                                        │  │
│  │  ┌─────────────────────────────────────────────────┐ │  │
│  │  │ Company A (Sipuni)                              │ │  │
│  │  │  - company.sipcrm.uz                            │ │  │
│  │  │  - Users: 15 (3 admins, 5 managers, 7 ops)      │ │  │
│  │  │  - Calls: ~150/day                              │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  │                                                        │  │
│  │  ┌─────────────────────────────────────────────────┐ │  │
│  │  │ Company B (Binotel)                             │ │  │
│  │  │  - companyb.sipcrm.uz                           │ │  │
│  │  │  - Users: 8 (1 admin, 2 managers, 5 ops)        │ │  │
│  │  │  - Calls: ~80/day                               │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ OWNER 2 (admin@example.com)                          │  │
│  │  ┌─────────────────────────────────────────────────┐ │  │
│  │  │ Company C (Sipuni)                              │ │  │
│  │  │  ...                                             │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Key Rules

1. **One Owner → Many Companies** (1:N)
2. **One Company → Exactly One Provider** (Sipuni OR Binotel)
3. **One User → Exactly One Company** (1:1)
4. **If business needs both providers** → Create 2 separate Companies

### Tenant Isolation

- **Database Level:** All tables have `company_id` foreign key
- **Application Level:** All queries filtered by `company_id` from JWT
- **Row-Level Security:** PostgreSQL RLS policies (future optimization)

---

## 3. DATABASE SCHEMA

### 3.1 Core Entity-Relationship Diagram

```
┌──────────────┐
│   owners     │
│──────────────│
│ id (PK)      │──┐
│ email        │  │
│ password_hash│  │
│ first_name   │  │
│ last_name    │  │
│ is_active    │  │
│ created_at   │  │
└──────────────┘  │
                   │
         ┌─────────┘
         │ 1:N
         ↓
┌──────────────────────┐
│     companies        │
│──────────────────────│
│ id (PK)              │──┐
│ owner_id (FK)        │  │
│ name                 │  │
│ subdomain            │  │ UNIQUE
│ provider_type        │  │ (sipuni|binotel)
│ provider_config      │  │ JSONB
│ timezone             │  │
│ locale               │  │
│ is_active            │  │
│ created_at           │  │
└──────────────────────┘  │
                           │
         ┌─────────────────┤
         │ 1:N             │ 1:N
         ↓                 ↓
┌──────────────────┐  ┌──────────────────┐
│      users       │  │    call_events   │
│──────────────────│  │──────────────────│
│ id (PK)          │  │ id (PK) INTEGER  │
│ company_id (FK)  │  │ company_id (FK)  │
│ email            │  │ provider_type    │
│ password_hash    │  │ provider_call_id │
│ first_name       │  │ phone_1          │
│ last_name        │  │ phone_2          │
│ role             │  │ operator_id (FK) │
│ permissions      │  │ state            │
│ language         │  │ waiting_sec      │
│ is_active        │  │ billing_sec      │
│ deleted_at       │  │ record_url       │
│ created_at       │  │ created_at       │
└──────────────────┘  └──────────────────┘
         │
         │ 1:N
         ↓
┌──────────────────┐       ┌──────────────────┐
│      leads       │       │     contacts     │
│──────────────────│       │──────────────────│
│ id (PK)          │       │ id (PK)          │
│ company_id (FK)  │       │ company_id (FK)  │
│ assigned_to (FK) │       │ phone            │
│ source           │       │ email            │
│ status           │       │ first_name       │
│ phone            │       │ last_name        │
│ email            │       │ company_name     │
│ pipeline_stage   │       │ created_by (FK)  │
│ deleted_at       │       │ deleted_at       │
│ created_at       │       │ created_at       │
└──────────────────┘       └──────────────────┘
         │
         │ 1:N
         ↓
┌──────────────────┐       ┌──────────────────┐
│      deals       │       │      tasks       │
│──────────────────│       │──────────────────│
│ id (PK)          │       │ id (PK)          │
│ company_id (FK)  │       │ company_id (FK)  │
│ lead_id (FK)     │       │ assigned_to (FK) │
│ contact_id (FK)  │       │ title            │
│ assigned_to (FK) │       │ description      │
│ amount           │       │ due_date         │
│ currency         │       │ status           │
│ stage            │       │ priority         │
│ probability      │       │ completed_at     │
│ deleted_at       │       │ deleted_at       │
│ created_at       │       │ created_at       │
└──────────────────┘       └──────────────────┘

┌──────────────────┐       ┌──────────────────┐
│      notes       │       │   audit_logs     │
│──────────────────│       │──────────────────│
│ id (PK)          │       │ id (PK)          │
│ company_id (FK)  │       │ company_id (FK)  │
│ entity_type      │       │ user_id (FK)     │
│ entity_id        │       │ action           │
│ created_by (FK)  │       │ entity_type      │
│ content          │       │ entity_id        │
│ deleted_at       │       │ before JSONB     │
│ created_at       │       │ after JSONB      │
└──────────────────┘       │ created_at       │
                            └──────────────────┘
```

### 3.2 Detailed Table Schemas

#### owners
```sql
CREATE TABLE owners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(225),
    last_name VARCHAR(225),
    phone VARCHAR(50),
    is_active BOOLEAN DEFAULT FALSE,
    is_suspended BOOLEAN DEFAULT FALSE,
    email_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_owners_email ON owners(email);
```

#### companies
```sql
CREATE TYPE provider_enum AS ENUM ('sipuni', 'binotel');

CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    subdomain VARCHAR(100) UNIQUE NOT NULL,
    provider_type provider_enum NOT NULL,

    -- Provider-specific configurations stored as JSONB
    -- For Sipuni: {cabinet_id, security_key, token}
    -- For Binotel: {api_key, api_secret, internal_number}
    provider_config JSONB NOT NULL DEFAULT '{}',

    -- Localization
    timezone VARCHAR(50) DEFAULT 'Asia/Tashkent',
    locale VARCHAR(10) DEFAULT 'en',

    -- Business info
    phone VARCHAR(50),
    address TEXT,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    deleted_at TIMESTAMP NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_companies_owner_id ON companies(owner_id);
CREATE INDEX idx_companies_subdomain ON companies(subdomain);
CREATE INDEX idx_companies_provider_type ON companies(provider_type);
```

#### users (Modified from existing)
```sql
CREATE TYPE role_enum AS ENUM ('owner', 'company_admin', 'company_manager', 'company_operator');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(225),
    last_name VARCHAR(225),
    phone VARCHAR(50),

    -- Role & Permissions
    role role_enum NOT NULL DEFAULT 'company_operator',
    permissions JSONB DEFAULT '[]',  -- ["leads.read", "calls.write"]

    -- Localization
    language VARCHAR(10) DEFAULT 'en',

    -- Status
    is_active BOOLEAN DEFAULT FALSE,
    is_suspended BOOLEAN DEFAULT FALSE,
    email_verified BOOLEAN DEFAULT FALSE,

    -- Soft delete
    deleted_at TIMESTAMP NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_id, email)
);

CREATE INDEX idx_users_company_id ON users(company_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

#### call_events (Unified for all providers)
```sql
CREATE TYPE call_state_enum AS ENUM ('ANSWER', 'BUSY', 'NOANSWER', 'CANCEL', 'CONGESTION', 'CHANUNAVAIL');

CREATE TABLE call_events (
    id INTEGER PRIMARY KEY,  -- Company-scoped sequential (via next_call_number())
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Provider info
    provider_type provider_enum NOT NULL,
    call_number INTEGER,  -- Company-scoped sequential number
    provider_call_id VARCHAR(255) NOT NULL,  -- Prefixed: sipuni_<id>, binotel_<id>

    -- Call participants
    phone_1 VARCHAR(50),  -- Caller
    phone_2 VARCHAR(50),  -- Receiver
    operator_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Call metadata
    direction VARCHAR(20),  -- inbound, outbound, internal
    state call_state_enum,
    attempts INTEGER DEFAULT 1,
    waiting_sec INTEGER,
    billing_sec INTEGER,

    -- Recording
    record_url TEXT,

    -- Timestamps
    call_start_timestamp BIGINT,
    call_end_timestamp BIGINT,

    -- CRM Integration
    contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,

    -- UTM tracking
    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_id, provider_type, provider_call_id)
);

CREATE INDEX idx_call_events_company_id ON call_events(company_id);
CREATE INDEX idx_call_events_operator_id ON call_events(operator_id);
CREATE INDEX idx_call_events_contact_id ON call_events(contact_id);
CREATE INDEX idx_call_events_phone_1 ON call_events(phone_1);
CREATE INDEX idx_call_events_created_at ON call_events(created_at);
```

#### contacts
```sql
CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Contact info
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    company_name VARCHAR(255),
    phone VARCHAR(50),
    email VARCHAR(255),

    -- Additional fields
    position VARCHAR(255),
    source VARCHAR(100),  -- website, call, manual, import
    tags JSONB DEFAULT '[]',
    custom_fields JSONB DEFAULT '{}',

    -- Assignment
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Soft delete
    deleted_at TIMESTAMP NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_contacts_company_id ON contacts(company_id);
CREATE INDEX idx_contacts_phone ON contacts(phone);
CREATE INDEX idx_contacts_email ON contacts(email);
CREATE INDEX idx_contacts_assigned_to ON contacts(assigned_to);
```

#### leads
```sql
CREATE TYPE lead_status_enum AS ENUM ('new', 'contacted', 'qualified', 'converted', 'lost');
CREATE TYPE pipeline_stage_enum AS ENUM ('new', 'contact_made', 'meeting_scheduled', 'proposal_sent', 'negotiation', 'won', 'lost');

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,

    -- Lead info
    title VARCHAR(255) NOT NULL,
    description TEXT,
    source VARCHAR(100),  -- website, referral, call, campaign
    status lead_status_enum DEFAULT 'new',
    pipeline_stage pipeline_stage_enum DEFAULT 'new',

    -- Value
    estimated_value DECIMAL(15, 2),
    currency VARCHAR(10) DEFAULT 'USD',

    -- Assignment
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Metadata
    tags JSONB DEFAULT '[]',
    custom_fields JSONB DEFAULT '{}',

    -- Soft delete
    deleted_at TIMESTAMP NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_leads_company_id ON leads(company_id);
CREATE INDEX idx_leads_contact_id ON leads(contact_id);
CREATE INDEX idx_leads_assigned_to ON leads(assigned_to);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_pipeline_stage ON leads(pipeline_stage);
```

#### deals
```sql
CREATE TYPE deal_stage_enum AS ENUM ('prospecting', 'qualification', 'proposal', 'negotiation', 'closed_won', 'closed_lost');

CREATE TABLE deals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,

    -- Deal info
    title VARCHAR(255) NOT NULL,
    description TEXT,
    amount DECIMAL(15, 2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD',
    stage deal_stage_enum DEFAULT 'prospecting',
    probability INTEGER DEFAULT 0,  -- 0-100

    -- Dates
    expected_close_date DATE,
    closed_date DATE,

    -- Assignment
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Metadata
    tags JSONB DEFAULT '[]',
    custom_fields JSONB DEFAULT '{}',

    -- Soft delete
    deleted_at TIMESTAMP NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_deals_company_id ON deals(company_id);
CREATE INDEX idx_deals_assigned_to ON deals(assigned_to);
CREATE INDEX idx_deals_stage ON deals(stage);
```

#### tasks
```sql
CREATE TYPE task_status_enum AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');
CREATE TYPE task_priority_enum AS ENUM ('low', 'medium', 'high', 'urgent');

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Task info
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status task_status_enum DEFAULT 'pending',
    priority task_priority_enum DEFAULT 'medium',

    -- Dates
    due_date TIMESTAMP,
    completed_at TIMESTAMP,

    -- Relations
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Linked entities
    entity_type VARCHAR(50),  -- 'lead', 'contact', 'deal'
    entity_id UUID,

    -- Soft delete
    deleted_at TIMESTAMP NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_company_id ON tasks(company_id);
CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_due_date ON tasks(due_date);
```

#### notes
```sql
CREATE TABLE notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Note content
    content TEXT NOT NULL,

    -- Relations
    entity_type VARCHAR(50) NOT NULL,  -- 'lead', 'contact', 'deal', 'call'
    entity_id UUID NOT NULL,

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Soft delete
    deleted_at TIMESTAMP NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notes_company_id ON notes(company_id);
CREATE INDEX idx_notes_entity ON notes(entity_type, entity_id);
CREATE INDEX idx_notes_created_by ON notes(created_by);
```

#### audit_logs
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Action info
    action VARCHAR(50) NOT NULL,  -- 'create', 'update', 'delete', 'login'
    entity_type VARCHAR(50),  -- 'lead', 'contact', 'user'
    entity_id UUID,

    -- Changes
    before JSONB,
    after JSONB,

    -- Request metadata
    ip_address VARCHAR(50),
    user_agent TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_company_id ON audit_logs(company_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
```

#### tags
```sql
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    name VARCHAR(100) NOT NULL,
    color VARCHAR(7) DEFAULT '#3B82F6',  -- Hex color

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_id, name)
);

CREATE INDEX idx_tags_company_id ON tags(company_id);
```

#### attachments
```sql
CREATE TABLE attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- File info
    filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR(100),

    -- Relations
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,

    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_attachments_company_id ON attachments(company_id);
CREATE INDEX idx_attachments_entity ON attachments(entity_type, entity_id);
```

---

## 4. AUTHENTICATION & AUTHORIZATION

### 4.1 JWT Token Structure

#### Owner Token (for platform-level access)
```json
{
  "sub": "owner_uuid",
  "type": "owner",
  "owner_id": "owner_uuid",
  "email": "owner@example.com",
  "exp": 1234567890
}
```

#### Company User Token
```json
{
  "sub": "user_uuid",
  "type": "user",
  "role": "company_operator",
  "owner_id": "owner_uuid",
  "company_id": "company_uuid",
  "permissions": [
    "calls.read",
    "leads.read",
    "leads.write",
    "contacts.read"
  ],
  "exp": 1234567890
}
```

### 4.2 Permission Model

#### Permission Naming Convention
```
{resource}.{action}

Examples:
- leads.read
- leads.write
- leads.delete
- calls.read
- calls.write
- stats.read
- users.manage
- settings.manage
```

#### Role-Permission Matrix

| Permission | Owner | Company Admin | Company Manager | Company Operator |
|------------|-------|---------------|-----------------|------------------|
| leads.read | ✅ | ✅ | ✅ | ✅ |
| leads.write | ✅ | ✅ | ✅ | ❌ |
| leads.delete | ✅ | ✅ | ❌ | ❌ |
| contacts.read | ✅ | ✅ | ✅ | ✅ |
| contacts.write | ✅ | ✅ | ✅ | ❌ |
| calls.read | ✅ | ✅ | ✅ | ✅ |
| calls.write | ✅ | ✅ | ✅ | ✅ |
| stats.read | ✅ | ✅ | ✅ | ❌ |
| users.manage | ✅ | ✅ | ❌ | ❌ |
| settings.manage | ✅ | ✅ | ❌ | ❌ |
| company.delete | ✅ | ❌ | ❌ | ❌ |

### 4.3 Authorization Middleware

```python
from functools import wraps
from fastapi import HTTPException, status

def require_permissions(*required_permissions: str):
    """
    Decorator for endpoints requiring specific permissions

    Usage:
        @router.get("/leads")
        @require_permissions("leads.read")
        async def get_leads(user: User = User.current()):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get('user')
            user_permissions = set(user.permissions or [])

            # Owners have all permissions
            if user.role == 'owner':
                return await func(*args, **kwargs)

            # Check if user has all required permissions
            if not all(perm in user_permissions for perm in required_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

### 4.4 Multi-Tenant Data Isolation

**Automatic company_id filtering:**

```python
class CompanyMixin:
    """Mixin for models with company_id"""

    @classmethod
    async def get_for_company(cls, company_id: UUID, **filters):
        """Get records filtered by company_id"""
        async with get_session() as session:
            stmt = select(cls).filter_by(
                company_id=company_id,
                deleted_at=None,
                **filters
            )
            result = await session.execute(stmt)
            return result.scalars().all()
```

---

## 5. TELEPHONY PROVIDER ABSTRACTION

### 5.1 Abstract Base Class

```python
# source/utils/services/telephony/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel

class CallRequest(BaseModel):
    phone_1: str
    phone_2: str
    order_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

class CallStatus(BaseModel):
    provider_call_id: str
    state: str
    waiting_sec: Optional[int] = None
    billing_sec: Optional[int] = None
    record_url: Optional[str] = None
    call_start: Optional[datetime] = None
    call_end: Optional[datetime] = None

class TelephonyProvider(ABC):
    """Abstract base class for telephony providers"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with company-specific config

        Args:
            config: Provider configuration from companies.provider_config
        """
        self.config = config

    @abstractmethod
    async def make_call(
        self,
        request: CallRequest
    ) -> Dict[str, Any]:
        """
        Initiate a call

        Returns:
            {
                "success": bool,
                "call_id": str,
                "message": str
            }
        """
        pass

    @abstractmethod
    async def get_call_status(
        self,
        call_id: str
    ) -> CallStatus:
        """
        Get call status by provider_call_id
        """
        pass

    @abstractmethod
    async def get_call_record_url(
        self,
        call_id: str
    ) -> Optional[str]:
        """
        Get call recording URL
        """
        pass

    @abstractmethod
    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Process incoming webhook from provider

        Returns normalized call event data or None if not a valid webhook
        """
        pass

    @abstractmethod
    async def validate_webhook_auth(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> bool:
        """
        Validate webhook authentication
        """
        pass
```

### 5.2 Provider Factory

```python
# source/utils/services/telephony/factory.py

from typing import Dict, Any
from .base import TelephonyProvider
from .sipuni_provider import SipuniProvider
from .binotel_provider import BinotelProvider

class ProviderFactory:
    """Factory for creating telephony provider instances"""

    _providers = {
        'sipuni': SipuniProvider,
        'binotel': BinotelProvider,
    }

    @classmethod
    def create(
        cls,
        provider_type: str,
        config: Dict[str, Any]
    ) -> TelephonyProvider:
        """
        Create provider instance

        Args:
            provider_type: 'sipuni' or 'binotel'
            config: Provider configuration from companies.provider_config

        Returns:
            TelephonyProvider instance

        Raises:
            ValueError: If provider_type is not supported
        """
        provider_class = cls._providers.get(provider_type)

        if not provider_class:
            raise ValueError(
                f"Unsupported provider: {provider_type}. "
                f"Supported providers: {list(cls._providers.keys())}"
            )

        return provider_class(config)

    @classmethod
    def register_provider(
        cls,
        provider_type: str,
        provider_class: type
    ):
        """Register a new provider implementation"""
        cls._providers[provider_type] = provider_class
```

### 5.3 Usage in Controllers

```python
# source/api/v1/routers/company/calls.py

from source.utils.services.telephony.factory import ProviderFactory
from source.db.models.company import Company

@router.post("/company/call")
async def make_call(
    request: CallRequest,
    user: User = User.current()
):
    # Get user's company
    company = await Company.get_or_404(id=user.company_id)

    # Create provider instance
    provider = ProviderFactory.create(
        provider_type=company.provider_type,
        config=company.provider_config
    )

    # Make call (provider-agnostic)
    result = await provider.make_call(request)

    # Store call event
    await CallEvent.create(
        company_id=company.id,
        provider_type=company.provider_type,
        provider_call_id=result['call_id'],
        phone_1=request.phone_1,
        phone_2=request.phone_2,
        operator_id=user.id,
        utm_source=request.utm_source,
        utm_medium=request.utm_medium,
        utm_campaign=request.utm_campaign
    )

    return result
```

---

## 6. API ROUTING STRUCTURE

### 6.1 New Route Organization

```
/api/v1
├── /auth
│   ├── POST /register           # User registration
│   ├── POST /login              # User login
│   ├── POST /refresh            # Refresh token
│   ├── POST /forgot-password    # Request reset
│   ├── POST /reset-password     # Confirm reset
│   └── POST /verify-email       # Email verification
│
├── /owners                      # Owner-level operations
│   ├── POST /register           # Owner registration
│   ├── GET /profile             # Owner profile
│   ├── PATCH /profile           # Update profile
│   └── GET /companies           # List all companies (owner's)
│
├── /companies                   # Company management
│   ├── POST /                   # Create company
│   ├── GET /                    # List companies (owner context)
│   ├── GET /{id}                # Get company details
│   ├── PATCH /{id}              # Update company
│   ├── DELETE /{id}             # Delete company (soft)
│   └── POST /{id}/regenerate-webhook-token
│
├── /company                     # Current company operations (from JWT)
│   │
│   ├── /calls                   # Call operations (sub-package)
│   │   ├── POST /               # Make call (provider-agnostic)
│   │   ├── GET /                # List calls
│   │   ├── GET /{id}            # Get call details
│   │   ├── PUT /{id}/outcome    # Set call outcome
│   │   ├── POST /{id}/link      # Link call to CRM entity
│   │   ├── GET /history         # Call history
│   │   ├── GET /outcomes/summary # Outcome stats
│   │   ├── GET /auto-link-suggestions/{phone}
│   │   ├── /sipuni/             # Sipuni-specific
│   │   │   ├── POST /external   # External call
│   │   │   ├── POST /number     # Call by number
│   │   │   ├── POST /tree       # Call tree
│   │   │   └── POST /{id}/cancel # Cancel call
│   │   └── /binotel/            # Binotel-specific
│   │
│   ├── /recordings              # Call recordings
│   │   └── GET /{call_id}       # Authenticated streaming
│   │
│   ├── /webhooks                # Webhook receivers
│   │   └── GET /{token}         # Unified webhook (GET, IP whitelisted)
│   │
│   ├── /users                   # User management
│   │   ├── POST /               # Create user
│   │   ├── GET /                # List users
│   │   ├── GET /{id}            # Get user
│   │   ├── PATCH /{id}          # Update user
│   │   ├── DELETE /{id}         # Delete user (soft)
│   │   └── PATCH /{id}/permissions
│   │
│   ├── /contacts
│   │   ├── POST /
│   │   ├── GET /
│   │   ├── GET /{id}
│   │   ├── PATCH /{id}
│   │   ├── DELETE /{id}
│   │   ├── POST /import         # CSV import
│   │   └── GET /export          # CSV export
│   │
│   ├── /leads
│   │   ├── POST /
│   │   ├── GET /
│   │   ├── GET /{id}
│   │   ├── PATCH /{id}
│   │   ├── DELETE /{id}
│   │   ├── PATCH /{id}/stage    # Update pipeline stage
│   │   └── PATCH /{id}/assign   # Assign to user
│   │
│   ├── /deals
│   │   ├── POST /
│   │   ├── GET /
│   │   ├── GET /{id}
│   │   ├── PATCH /{id}
│   │   └── DELETE /{id}
│   │
│   ├── /tasks
│   │   ├── POST /
│   │   ├── GET /
│   │   ├── GET /{id}
│   │   ├── PATCH /{id}
│   │   ├── DELETE /{id}
│   │   └── PATCH /{id}/complete
│   │
│   ├── /notes
│   │   ├── POST /
│   │   ├── GET /               # ?entity_type=lead&entity_id=...
│   │   ├── GET /{id}
│   │   ├── PATCH /{id}
│   │   └── DELETE /{id}
│   │
│   ├── /tags
│   │   ├── POST /
│   │   ├── GET /
│   │   ├── PATCH /{id}
│   │   └── DELETE /{id}
│   │
│   ├── /attachments
│   │   ├── POST /              # Upload file
│   │   ├── GET /{id}           # Download file
│   │   └── DELETE /{id}
│   │
│   ├── /analytics              # Analytics
│   │   ├── GET /me             # My stats
│   │   ├── GET /me/dashboard   # My dashboard
│   │   ├── GET /team           # Team stats
│   │   ├── GET /team/dashboard # Team dashboard
│   │   ├── GET /operator/{id}  # Operator stats
│   │   └── DELETE /cache       # Clear analytics cache
│   │
│   ├── /contract               # Contract view
│   │
│   └── /permission-groups      # Permission groups
│
└── /admin                      # Platform admin (future)
    └── /stats                  # Cross-company analytics
```

### 6.2 Unified Webhook Endpoint

**Before (Sipuni-specific):**
```
GET /api/v1/sipuni/stream/{sipuni_id}/
```

**After (Provider-agnostic):**
```
GET /api/v1/company/webhooks/{token}
```

**Implementation:**
```python
@router.get("/company/webhooks/{token}")
async def handle_webhook(
    token: str,
    request: Request
):
    # Payload comes from query params (GET)
    payload = dict(request.query_params)
    # 1. Find company by webhook token
    company = await Company.get_one(webhook_token=token)
    if not company:
        raise HTTPException(404, "Invalid webhook token")

    # 2. Create provider instance
    provider = ProviderFactory.create(
        provider_type=company.provider_type,
        config=company.provider_config
    )

    # 3. Validate webhook authentication
    headers = dict(request.headers)
    if not await provider.validate_webhook_auth(payload, headers):
        raise HTTPException(403, "Webhook authentication failed")

    # 4. Handle webhook (provider-specific logic)
    call_data = await provider.handle_webhook(payload, headers)

    if not call_data:
        return {"status": "ignored"}

    # 5. Store/update call event
    await CallEvent.create_or_update(
        company_id=company.id,
        **call_data
    )

    return {"status": "success"}
```

---

## 7. BINOTEL INTEGRATION

### 7.1 Binotel Provider Implementation

```python
# source/utils/services/telephony/binotel_provider.py

import aiohttp
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime
from .base import TelephonyProvider, CallRequest, CallStatus

class BinotelProvider(TelephonyProvider):
    """
    Binotel telephony provider implementation

    Config structure:
    {
        "api_key": "your_api_key",
        "api_secret": "your_api_secret",
        "internal_number": "100"  # Default internal number for calls
    }
    """

    BASE_URL = "https://api.binotel.com"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.api_secret = config.get('api_secret')
        self.internal_number = config.get('internal_number', '100')

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate API signature"""
        sorted_params = sorted(params.items())
        param_string = ''.join(f"{k}{v}" for k, v in sorted_params)
        signature_string = f"{self.api_secret}{param_string}{self.api_secret}"
        return hashlib.md5(signature_string.encode()).hexdigest()

    async def _make_request(
        self,
        endpoint: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make authenticated API request"""
        params['key'] = self.api_key
        params['signature'] = self._generate_signature(params)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.BASE_URL}/{endpoint}",
                json=params
            ) as response:
                return await response.json()

    async def make_call(self, request: CallRequest) -> Dict[str, Any]:
        """
        Initiate external call via Binotel

        API: /api/externalCall.json
        """
        params = {
            "externalNumber": request.phone_1,  # Customer phone
            "internalNumber": self.internal_number,  # Operator
            "lineNumber": request.phone_2,  # Company line
        }

        if request.order_id:
            params["customerID"] = request.order_id

        result = await self._make_request("api/externalCall.json", params)

        return {
            "success": result.get("status") == "success",
            "call_id": result.get("callID", ""),
            "message": result.get("message", "")
        }

    async def get_call_status(self, call_id: str) -> CallStatus:
        """
        Get call status by generalCallID

        API: /api/stats/call-history.json
        """
        params = {
            "generalCallID": call_id
        }

        result = await self._make_request("api/stats/call-history.json", params)

        if not result.get('calls'):
            return None

        call = result['calls'][0]

        return CallStatus(
            provider_call_id=call_id,
            state=call.get('disposition', 'UNKNOWN'),
            waiting_sec=call.get('waitTime'),
            billing_sec=call.get('billsec'),
            record_url=call.get('recordingLink'),
            call_start=datetime.fromtimestamp(call.get('startTime', 0)),
            call_end=datetime.fromtimestamp(call.get('endTime', 0))
        )

    async def get_call_record_url(self, call_id: str) -> Optional[str]:
        """Get call recording URL"""
        status = await self.get_call_status(call_id)
        return status.record_url if status else None

    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Process Binotel webhook (apiCallCompleted event)

        Webhook structure:
        {
            "eventType": "apiCallCompleted",
            "generalCallID": "123456",
            "externalNumber": "998901234567",
            "internalNumber": "100",
            "disposition": "ANSWER",
            "billsec": 120,
            "waitTime": 5,
            "recordingLink": "https://...",
            "startTime": 1234567890,
            "endTime": 1234567900
        }
        """
        if payload.get('eventType') != 'apiCallCompleted':
            return None

        return {
            "provider_call_id": payload.get('generalCallID'),
            "phone_1": payload.get('externalNumber'),
            "phone_2": payload.get('internalNumber'),
            "state": payload.get('disposition'),
            "billing_sec": payload.get('billsec'),
            "waiting_sec": payload.get('waitTime'),
            "record_url": payload.get('recordingLink'),
            "call_start_timestamp": payload.get('startTime'),
            "call_end_timestamp": payload.get('endTime'),
            "direction": "outbound"  # Binotel external calls are outbound
        }

    async def validate_webhook_auth(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> bool:
        """
        Validate Binotel webhook

        Binotel uses IP whitelisting, similar to Sipuni
        Configure BINOTEL_ALLOWED_IPS in environment
        """
        # For MVP, return True
        # In production, implement IP whitelisting
        return True
```

### 7.2 Sipuni Provider (Refactored)

```python
# source/utils/services/telephony/sipuni_provider.py

import aiohttp
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime
from .base import TelephonyProvider, CallRequest, CallStatus

class SipuniProvider(TelephonyProvider):
    """
    Sipuni telephony provider implementation

    Config structure:
    {
        "cabinet_id": "12345",
        "security_key": "secret_key",
        "token": "webhook_token"  # For webhook validation
    }
    """

    BASE_URL = "https://sipuni.com/api/statistic"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.cabinet_id = config.get('cabinet_id')
        self.security_key = config.get('security_key')
        self.webhook_token = config.get('token')

    def _generate_hash(self, params: Dict[str, str]) -> str:
        """Generate MD5 hash for authentication"""
        sorted_params = sorted(params.items())
        param_string = ''.join(f"{k}{v}" for k, v in sorted_params)
        hash_string = f"{param_string}{self.security_key}"
        return hashlib.md5(hash_string.encode()).hexdigest()

    async def _make_request(
        self,
        endpoint: str,
        params: Dict[str, str]
    ) -> Dict[str, Any]:
        """Make authenticated API request"""
        params['user'] = self.cabinet_id
        params['hash'] = self._generate_hash(params)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params
            ) as response:
                return await response.json()

    async def make_call(self, request: CallRequest) -> Dict[str, Any]:
        """
        Initiate call via Sipuni

        For external calls: /externalCall
        """
        params = {
            "from": request.phone_1,
            "to": request.phone_2,
        }

        if request.order_id:
            params["numberId"] = request.order_id

        result = await self._make_request("externalCall", params)

        return {
            "success": result.get("result") == True,
            "call_id": result.get("callID", ""),
            "message": result.get("message", "")
        }

    async def get_call_status(self, call_id: str) -> CallStatus:
        """Get call status"""
        # Implementation similar to existing stream.py logic
        # This would query Sipuni API for call details
        pass

    async def get_call_record_url(self, call_id: str) -> Optional[str]:
        """Get call recording URL"""
        # Query call_events table for record_link
        pass

    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Process Sipuni webhook (stream event)

        Only process hangup events (event=2)
        """
        if payload.get('event') != 2:
            return None

        return {
            "provider_call_id": payload.get('call_id'),
            "phone_1": payload.get('src_num'),
            "phone_2": payload.get('pbxdstnum'),
            "state": payload.get('status'),
            "call_start_timestamp": payload.get('call_start_timestamp'),
            "call_end_timestamp": payload.get('call_end_timestamp'),
            "record_url": payload.get('record_link'),
            # ... map other fields
        }

    async def validate_webhook_auth(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> bool:
        """
        Validate Sipuni webhook by IP whitelist
        """
        # Check source IP against SIPUNI_ALLOWED_IPS
        return True  # For MVP
```

---

## 8. LOCALIZATION

### 8.1 Supported Regions

#### Central Asia
- 🇰🇿 Kazakhstan (kk, ru, en)
- 🇰🇬 Kyrgyzstan (ky, ru, en)
- 🇹🇯 Tajikistan (tg, ru, en)
- 🇹🇲 Turkmenistan (tk, ru, en)
- 🇺🇿 Uzbekistan (uz, ru, en)

#### CIS & Neighbors
- 🇷🇺 Russia (ru, en)
- 🇺🇦 Ukraine (uk, ru, en)
- 🇧🇾 Belarus (be, ru, en)
- 🇲🇩 Moldova (ro, ru, en)

#### Baltics
- 🇪🇪 Estonia (et, ru, en)
- 🇱🇻 Latvia (lv, ru, en)
- 🇱🇹 Lithuania (lt, ru, en)

#### South Caucasus
- 🇦🇲 Armenia (hy, ru, en)
- 🇦🇿 Azerbaijan (az, ru, en)
- 🇬🇪 Georgia (ka, ru, en)

### 8.2 Translation System

**Database Structure:**
```sql
CREATE TABLE translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(255) NOT NULL,
    locale VARCHAR(10) NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(key, locale)
);

CREATE INDEX idx_translations_key ON translations(key);
CREATE INDEX idx_translations_locale ON translations(locale);
```

**Translation Service:**
```python
# source/utils/services/translation_service.py

class TranslationService:
    """Translation service with caching"""

    _cache: Dict[str, Dict[str, str]] = {}

    @classmethod
    async def get(
        cls,
        key: str,
        locale: str = 'en',
        **kwargs
    ) -> str:
        """
        Get translation for key

        Args:
            key: Translation key (e.g., 'auth.login_success')
            locale: Language code
            **kwargs: Format variables

        Returns:
            Translated string
        """
        if locale not in cls._cache:
            await cls._load_locale(locale)

        value = cls._cache.get(locale, {}).get(key, key)

        if kwargs:
            return value.format(**kwargs)

        return value

    @classmethod
    async def _load_locale(cls, locale: str):
        """Load translations from database into cache"""
        async with get_session() as session:
            stmt = select(Translation).filter_by(locale=locale)
            result = await session.execute(stmt)
            translations = result.scalars().all()

            cls._cache[locale] = {
                t.key: t.value for t in translations
            }
```

**Usage in endpoints:**
```python
@router.post("/login")
async def login(
    credentials: LoginRequest,
    user_language: str = Header(None, alias="Accept-Language")
):
    # ... authentication logic ...

    message = await TranslationService.get(
        'auth.login_success',
        locale=user_language or 'en',
        username=user.first_name
    )

    return {
        "access_token": token,
        "message": message  # "Welcome back, John!"
    }
```

### 8.3 Timezone Handling

```python
# Store all timestamps in UTC
# Convert to user/company timezone on retrieval

from zoneinfo import ZoneInfo

def to_company_timezone(dt: datetime, company: Company) -> datetime:
    """Convert UTC datetime to company timezone"""
    return dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(
        ZoneInfo(company.timezone)
    )
```

---

## 9. STATISTICS & ANALYTICS

### 9.1 Real-Time Statistics (MVP)

#### Call Statistics
```sql
-- Total calls by company
SELECT
    company_id,
    COUNT(*) as total_calls,
    COUNT(*) FILTER (WHERE state = 'ANSWER') as answered_calls,
    COUNT(*) FILTER (WHERE state = 'NOANSWER') as missed_calls,
    AVG(billing_sec) FILTER (WHERE state = 'ANSWER') as avg_duration
FROM call_events
WHERE company_id = $1
  AND created_at >= $2  -- date_from
  AND created_at <= $3  -- date_to
GROUP BY company_id;
```

#### Per-Operator Statistics
```sql
SELECT
    u.id,
    u.first_name,
    u.last_name,
    COUNT(ce.id) as total_calls,
    COUNT(ce.id) FILTER (WHERE ce.state = 'ANSWER') as answered,
    COUNT(ce.id) FILTER (WHERE ce.state = 'NOANSWER') as missed,
    AVG(ce.billing_sec) FILTER (WHERE ce.state = 'ANSWER') as avg_duration,
    SUM(CASE WHEN d.id IS NOT NULL THEN d.amount ELSE 0 END) as revenue
FROM users u
LEFT JOIN call_events ce ON ce.operator_id = u.id
LEFT JOIN deals d ON d.assigned_to = u.id AND d.stage = 'closed_won'
WHERE u.company_id = $1
  AND ce.created_at >= $2
  AND ce.created_at <= $3
GROUP BY u.id, u.first_name, u.last_name
ORDER BY total_calls DESC;
```

### 9.2 Pre-Aggregated Tables (Future)

```sql
CREATE TABLE daily_call_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id),
    operator_id UUID REFERENCES users(id),
    date DATE NOT NULL,

    total_calls INTEGER DEFAULT 0,
    answered_calls INTEGER DEFAULT 0,
    missed_calls INTEGER DEFAULT 0,
    total_duration_sec INTEGER DEFAULT 0,
    avg_duration_sec INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_id, operator_id, date)
);

CREATE INDEX idx_daily_stats_company ON daily_call_stats(company_id);
CREATE INDEX idx_daily_stats_date ON daily_call_stats(date);
```

**Background Job (Celery):**
```python
@celery.task
def aggregate_daily_stats(date: str):
    """Run daily at midnight to aggregate previous day stats"""
    # Aggregate call_events into daily_call_stats
    pass
```

### 9.3 Statistics Endpoints

```python
# GET /api/v1/company/stats/calls
@router.get("/stats/calls")
@require_permissions("stats.read")
async def get_call_stats(
    date_from: date,
    date_to: date,
    user: User = User.current()
):
    """Get call statistics for date range"""
    # Query call_events with filters
    pass

# GET /api/v1/company/stats/operators
@router.get("/stats/operators")
@require_permissions("stats.read")
async def get_operator_stats(
    date_from: date,
    date_to: date,
    user: User = User.current()
):
    """Get per-operator statistics"""
    pass

# GET /api/v1/company/stats/dashboard
@router.get("/stats/dashboard")
async def get_dashboard(user: User = User.current()):
    """Get dashboard summary"""
    return {
        "total_calls_today": ...,
        "answered_calls_today": ...,
        "active_leads": ...,
        "deals_in_progress": ...,
        "revenue_this_month": ...,
    }
```

---

## 10. CALL RECORDING ACCESS (AUTHENTICATED STREAMING)

### 10.1 Problem Statement

**Security Issue:**
- Sipuni and Binotel provide direct S3/CDN URLs for call recordings
- Exposing these URLs reveals provider infrastructure
- URLs may contain sensitive tokens

**Solution:**
Authenticated streaming endpoint that fetches from provider and streams directly to the authenticated client. No external URLs are ever exposed.

### 10.2 Architecture

```
User Request (with JWT):
GET /api/v1/company/recordings/{call_id}
              ↓
         Validate JWT + CALLS_READ permission
              ↓
         Look up CallEvent.record_url from DB
              ↓
         Fetch from provider URL via HTTPClientPool (aiohttp)
              ↓
         StreamingResponse (64KB chunks) to client
```

### 10.3 Implementation

```python
# source/api/v1/routers/company/recordings.py

@router.get("/recordings/{call_id}")
@require_permissions(Permissions.CALLS_READ)
async def stream_recording(
    call_id: int,
    session: AsyncSession,
    user: User = User.current()
):
    """Stream call recording directly (authenticated)"""
    call = await CallEvent.get(session, id=call_id, company_id=user.company_id)
    if not call or not call.record_url:
        raise HTTPException(404, "Recording not found")

    # Fetch from provider via connection pool
    response = await HTTPClientPool.get(call.record_url, timeout=300)

    return StreamingResponse(
        response.content.iter_chunked(65536),  # 64KB chunks
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f'attachment; filename="recording_{call_id}.mp3"',
            "Content-Length": response.headers.get("Content-Length", ""),
        }
    )
```

### 10.4 HTTPClientPool

Singleton aiohttp-based HTTP client in `source/utils/services/telephony/http_client.py`:
- Connection pooling: 100 total connections, 20 per host
- DNS caching: 300s TTL
- Exponential backoff retry
- Replaces the earlier token-based Nginx proxy approach

---

## 11. BACKGROUND JOBS

### 11.1 Technology Choice (MVP)

**Option 1: Celery + Redis** (Recommended for MVP)
- Familiar, battle-tested
- Easy to set up
- Good for simple periodic tasks

**Option 2: APScheduler**
- Lightweight
- No extra infrastructure
- Limited scalability

**Decision: Use Celery**

### 11.2 Job Queue Structure

```python
# source/celery_app.py

from celery import Celery
from source.core.config import settings

celery = Celery(
    'sipcrm',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)
```

### 11.3 Background Tasks

#### Daily Statistics Aggregation
```python
# source/tasks/stats_tasks.py

from source.celery_app import celery

@celery.task
def aggregate_daily_stats():
    """
    Run daily at midnight UTC
    Aggregates previous day's call stats into daily_call_stats table
    """
    yesterday = date.today() - timedelta(days=1)

    # Aggregate by company and operator
    # INSERT INTO daily_call_stats ...
    pass

# Schedule in celery beat
celery.conf.beat_schedule = {
    'aggregate-daily-stats': {
        'task': 'source.tasks.stats_tasks.aggregate_daily_stats',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
    },
}
```

#### Sync Call Records
```python
@celery.task
def sync_call_records():
    """
    Periodic job to sync call records from providers
    For calls that haven't received webhooks yet
    """
    # For each company:
    #   1. Get recent call_events without record_url
    #   2. Query provider API for record URLs
    #   3. Update call_events
    pass
```

#### Email Notifications
```python
@celery.task
def send_email_notification(
    to: str,
    subject: str,
    template: str,
    context: Dict[str, Any]
):
    """
    Send email notification

    Usage:
        send_email_notification.delay(
            to=user.email,
            subject="New Lead Assigned",
            template="lead_assigned.html",
            context={"lead": lead, "user": user}
        )
    """
    # Render template
    # Send via SMTP
    pass
```

#### Task Reminders
```python
@celery.task
def check_task_reminders():
    """
    Run every 5 minutes
    Check for tasks due soon and send notifications
    """
    # Get tasks with due_date within next 15 minutes
    # Send notifications to assigned users
    pass
```

---

## 12. AUDIT LOGGING

### 12.1 Audit Log Middleware

```python
# source/middleware/audit_middleware.py

from fastapi import Request
from source.db.models.audit_log import AuditLog

async def audit_log_middleware(request: Request, call_next):
    """
    Middleware to log all state-changing operations

    Logs: POST, PATCH, PUT, DELETE requests
    """
    response = await call_next(request)

    # Only log state-changing methods
    if request.method in ['POST', 'PATCH', 'PUT', 'DELETE']:
        # Extract user from request state (set by auth middleware)
        user = getattr(request.state, 'user', None)

        if user:
            await AuditLog.create(
                company_id=user.company_id,
                user_id=user.id,
                action=request.method,
                entity_type=_extract_entity_type(request.url.path),
                ip_address=request.client.host,
                user_agent=request.headers.get('user-agent'),
                # before and after populated by model hooks
            )

    return response

def _extract_entity_type(path: str) -> str:
    """Extract entity type from URL path"""
    # /api/v1/company/leads/123 -> 'lead'
    parts = path.split('/')
    if len(parts) >= 5 and parts[3] == 'company':
        return parts[4].rstrip('s')  # Remove plural 's'
    return None
```

### 12.2 Model-Level Audit Hooks

```python
# source/db/mixins/auditable.py

from sqlalchemy import event
from source.db.models.audit_log import AuditLog

class AuditableMixin:
    """
    Mixin for models that should be audited

    Automatically captures before/after state on updates
    """

    @staticmethod
    def _to_dict(instance):
        """Convert model instance to dict"""
        return {
            c.name: getattr(instance, c.name)
            for c in instance.__table__.columns
        }

@event.listens_for(AuditableMixin, 'before_update', propagate=True)
def before_update_audit(mapper, connection, target):
    """Capture state before update"""
    target._audit_before = AuditableMixin._to_dict(target)

@event.listens_for(AuditableMixin, 'after_update', propagate=True)
def after_update_audit(mapper, connection, target):
    """Log changes after update"""
    before = getattr(target, '_audit_before', {})
    after = AuditableMixin._to_dict(target)

    # Store for middleware to use
    target._audit_changes = {
        'before': before,
        'after': after
    }
```

### 12.3 Audit Log Queries

```python
# GET /api/v1/company/audit-logs
@router.get("/audit-logs")
@require_permissions("settings.manage")
async def get_audit_logs(
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 50,
    user: User = User.current()
):
    """Get audit logs with filters"""
    filters = {"company_id": user.company_id}

    if entity_type:
        filters["entity_type"] = entity_type
    if entity_id:
        filters["entity_id"] = entity_id
    if user_id:
        filters["user_id"] = user_id

    logs = await AuditLog.get_all(
        **filters,
        limit=limit,
        order_by=AuditLog.created_at.desc()
    )

    return logs
```

---

## 13. NON-FUNCTIONAL REQUIREMENTS

### 13.1 Soft Delete Implementation

**All CRM entities must use soft delete:**

```python
# source/db/mixins/soft_delete.py

from datetime import datetime
from sqlalchemy import Column, DateTime

class SoftDeleteMixin:
    """Mixin for soft delete functionality"""

    deleted_at = Column(DateTime, nullable=True, default=None)

    @classmethod
    async def soft_delete(cls, id: UUID):
        """Soft delete record"""
        await cls.update_by(
            {"id": id},
            {"deleted_at": datetime.utcnow()}
        )

    @classmethod
    async def get_active(cls, **filters):
        """Get only non-deleted records"""
        return await cls.get_all(
            deleted_at=None,
            **filters
        )
```

**Usage:**
```python
# Delete a lead
await Lead.soft_delete(id=lead_id)

# Get active leads only
leads = await Lead.get_active(company_id=company.id)
```

### 13.2 Rate Limiting

```python
# source/middleware/rate_limit.py

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL
)

# Apply to FastAPI app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Usage in routes
@router.post("/company/webhooks/{token}")
@limiter.limit("100/minute")  # Max 100 webhook requests per minute
async def handle_webhook(request: Request, token: str):
    ...
```

### 13.3 Database Indexing Strategy

**Critical Indexes (Already defined in schema):**
- `company_id` on all multi-tenant tables
- `email` on users/owners tables
- `phone` on contacts and call_events
- `created_at` on time-series data (call_events, audit_logs)
- Composite indexes on frequent JOIN conditions

### 13.4 Caching Strategy

```python
# source/utils/cache.py

import redis.asyncio as redis
import json

class CacheService:
    """Redis cache service"""

    _redis = None

    @classmethod
    async def get_redis(cls):
        if not cls._redis:
            cls._redis = await redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        return cls._redis

    @classmethod
    async def get(cls, key: str):
        """Get cached value"""
        r = await cls.get_redis()
        value = await r.get(key)
        return json.loads(value) if value else None

    @classmethod
    async def set(
        cls,
        key: str,
        value: Any,
        expiry: int = 3600
    ):
        """Set cached value"""
        r = await cls.get_redis()
        await r.setex(key, expiry, json.dumps(value))

    @classmethod
    async def delete(cls, key: str):
        """Delete cached value"""
        r = await cls.get_redis()
        await r.delete(key)
```

**Cache Keys Convention:**
```
company:{company_id}:stats:calls:{date}
company:{company_id}:users
translation:{locale}
```

---

## 14. MIGRATION FROM EXISTING STRUCTURE

### 14.1 Database Migration Steps

1. **Create new tables** (owners, companies, unified call_events)
2. **Migrate existing data:**
   - Create default Owner for existing users
   - Create Company for each unique Sipuni integration
   - Move users to companies
   - Migrate sipuni table data to companies.provider_config
   - Migrate call_events to unified structure
3. **Drop old tables** (sipuni, old call_events)
4. **Update foreign keys and constraints**

### 14.2 Migration Script

```python
# alembic/versions/xxx_multi_tenant_migration.py

def upgrade():
    # 1. Create new tables
    op.create_table('owners', ...)
    op.create_table('companies', ...)
    op.create_table('new_call_events', ...)

    # 2. Migrate data
    # Create default owner
    op.execute("""
        INSERT INTO owners (id, email, password_hash, first_name, last_name, is_active)
        SELECT
            gen_random_uuid(),
            'default@sipcrm.uz',
            '',
            'Default',
            'Owner',
            true
        LIMIT 1
    """)

    # Create companies from Sipuni integrations
    op.execute("""
        INSERT INTO companies (
            id, owner_id, name, subdomain,
            provider_type, provider_config
        )
        SELECT
            s.id,
            (SELECT id FROM owners LIMIT 1),
            s.company_name,
            LOWER(REPLACE(s.company_name, ' ', '-')),
            'sipuni',
            jsonb_build_object(
                'cabinet_id', s.cabinet_id,
                'security_key', s.security_key,
                'token', s.token
            )
        FROM sipuni s
    """)

    # Link users to companies
    op.execute("""
        UPDATE users u
        SET company_id = s.id
        FROM sipuni s
        WHERE s.user_id = u.id
    """)

    # Migrate call events
    op.execute("""
        INSERT INTO new_call_events (
            id, company_id, provider_type, provider_call_id,
            phone_1, phone_2, state, ...
        )
        SELECT
            gen_random_uuid(),
            ce.sipuni_id,
            'sipuni',
            ce.call_id,
            ce.src_num,
            ce.pbxdstnum,
            ce.status,
            ...
        FROM call_events ce
    """)

    # 3. Drop old tables
    op.drop_table('sipuni')
    op.drop_table('call_events')

    # 4. Rename new_call_events to call_events
    op.rename_table('new_call_events', 'call_events')

def downgrade():
    # Reverse migration
    pass
```

---

## 15. DEPLOYMENT & INFRASTRUCTURE (MVP)

### 15.1 Technology Stack

**Application:**
- FastAPI (async Python web framework)
- PostgreSQL 16+ (with JSONB support)
- Redis 7+ (caching via CacheService + future Celery broker)
- aiohttp (async HTTP client with connection pooling via HTTPClientPool)
- Nginx (reverse proxy, future production deployment)

**Background Jobs:**
- Celery (task queue)
- Celery Beat (periodic tasks)

**Deployment:**
- Docker + Docker Compose (MVP)
- Single VPS (4-8 GB RAM, 2-4 CPUs)
- Supervisor (process management)

### 15.2 Docker Compose Structure

```yaml
# docker-compose.yml

version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: sipcrm
      POSTGRES_USER: sipcrm
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: .
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
    environment:
      DATABASE_URL: postgresql+asyncpg://sipcrm:${DB_PASSWORD}@postgres/sipcrm
      REDIS_URL: redis://redis:6379
      JWT_SECRET: ${JWT_SECRET}
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  celery_worker:
    build: .
    command: celery -A source.celery_app worker --loglevel=info
    environment:
      DATABASE_URL: postgresql+asyncpg://sipcrm:${DB_PASSWORD}@postgres/sipcrm
      REDIS_URL: redis://redis:6379
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  celery_beat:
    build: .
    command: celery -A source.celery_app beat --loglevel=info
    environment:
      DATABASE_URL: postgresql+asyncpg://sipcrm:${DB_PASSWORD}@postgres/sipcrm
      REDIS_URL: redis://redis:6379
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d
      - ./nginx/ssl:/etc/nginx/ssl
      - /var/cache/nginx:/var/cache/nginx
    depends_on:
      - api
    restart: unless-stopped

volumes:
  postgres_data:
```

### 15.3 Environment Variables

```bash
# .env

# Database
DATABASE_URL=postgresql+asyncpg://sipcrm:password@localhost/sipcrm

# Redis
REDIS_URL=redis://localhost:6379

# JWT
JWT_SECRET=your-super-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30

# SMTP (for emails)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@sipcrm.uz
SMTP_PASSWORD=your-smtp-password
SMTP_FROM=noreply@sipcrm.uz

# Sipuni
SIPUNI_ALLOWED_IPS=185.41.162.0/24,185.41.163.0/24

# Binotel
BINOTEL_ALLOWED_IPS=your-binotel-ip-ranges

# Call Records Proxy
RECORD_PROXY_SECRET=another-super-secret-key

# Application
DEBUG=false
ALLOWED_ORIGINS=https://sipcrm.uz,https://*.sipcrm.uz
```

---

## 16. DEVELOPER DOCUMENTATION

### 16.1 Quick Start

```bash
# 1. Clone repository
git clone https://github.com/yourorg/siptools.git
cd siptools

# 2. Install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Set up environment
cp .env.copy .env
# Edit .env with your configuration

# 4. Run database migrations
alembic upgrade head

# 5. Create initial data (optional)
python scripts/seed_data.py

# 6. Start development server
uvicorn main:app --reload

# 7. Access API docs
# http://localhost:8000/
```

### 16.2 Adding a New CRM Entity

**Step 1: Create Model**
```python
# source/db/models/my_entity.py

from sqlalchemy import Column, String, UUID, ForeignKey
from source.db.base import Base
from source.db.mixins.soft_delete import SoftDeleteMixin
from source.db.mixins.auditable import AuditableMixin

class MyEntity(Base, SoftDeleteMixin, AuditableMixin):
    __tablename__ = 'my_entities'

    id = Column(UUID, primary_key=True, server_default=text("gen_random_uuid()"))
    company_id = Column(UUID, ForeignKey('companies.id'), nullable=False)
    name = Column(String(255), nullable=False)
    # ... other fields
```

**Step 2: Create Migration**
```bash
alembic revision -m "add my_entity table"
# Edit migration file
alembic upgrade head
```

**Step 3: Create Schemas**
```python
# source/api/v1/schemas/my_entity.py

from pydantic import BaseModel
from uuid import UUID

class MyEntityCreate(BaseModel):
    name: str

class MyEntityUpdate(BaseModel):
    name: str | None = None

class MyEntityResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
```

**Step 4: Create Router**
```python
# source/api/v1/routers/company/my_entity.py

from fastapi import APIRouter
from source.db.models.my_entity import MyEntity

router = APIRouter()

@router.post("/")
@require_permissions("my_entity.write")
async def create_my_entity(
    data: MyEntityCreate,
    user: User = User.current()
):
    entity = await MyEntity.create(
        company_id=user.company_id,
        **data.dict()
    )
    return entity

# ... other CRUD endpoints
```

**Step 5: Register Router**
```python
# source/api/v1/routers/company/__init__.py

from .my_entity import router as my_entity_router

router.include_router(
    my_entity_router,
    prefix="/my-entities",
    tags=["My Entities"]
)
```

### 16.3 Adding a New Telephony Provider

**Step 1: Implement Provider Class**
```python
# source/utils/services/telephony/new_provider.py

from .base import TelephonyProvider

class NewProvider(TelephonyProvider):
    async def make_call(self, request: CallRequest):
        # Implement API call
        pass

    async def get_call_status(self, call_id: str):
        pass

    async def handle_webhook(self, payload, headers):
        # Normalize webhook data
        pass

    async def validate_webhook_auth(self, payload, headers):
        pass
```

**Step 2: Register Provider**
```python
# source/utils/services/telephony/factory.py

from .new_provider import NewProvider

ProviderFactory.register_provider('new_provider', NewProvider)
```

**Step 3: Update Database Enum**
```sql
ALTER TYPE provider_enum ADD VALUE 'new_provider';
```

### 16.4 Testing

```python
# tests/test_my_entity.py

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_my_entity(client: AsyncClient, auth_token: str):
    response = await client.post(
        "/api/v1/company/my-entities",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "Test Entity"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Test Entity"
```

---

## 17. FUTURE ROADMAP (POST-MVP)

### Phase 2: Advanced Features
- **Transcription**: Call transcription using Whisper/AssemblyAI
- **Sentiment Analysis**: Analyze call sentiment
- **Call Tagging**: Auto-tag calls based on content
- **Advanced Search**: Full-text search across entities
- **Email Integration**: IMAP/SMTP integration for email tracking
- **Calendar Integration**: Google Calendar/Outlook sync

### Phase 3: Scaling
- **Microservices**: Split into separate services (auth, crm, telephony)
- **Message Queue**: Replace Celery with Kafka for event streaming
- **Row-Level Security**: PostgreSQL RLS for tenant isolation
- **Read Replicas**: Database read scaling
- **CDN**: Static asset distribution

### Phase 4: Enterprise
- **SSO**: SAML/OIDC integration
- **Advanced Permissions**: Custom role builder
- **Webhooks**: Outgoing webhooks for integrations
- **API Rate Limiting**: Per-company rate limits
- **White-Label**: Custom branding per company

---

## 18. COST ESTIMATES (MONTHLY)

### Infrastructure (MVP)
- **VPS**: $20-40/month (Hetzner/DigitalOcean)
- **Database Backup**: $5/month (S3)
- **Domain**: $1/month
- **SSL**: Free (Let's Encrypt)
- **Total**: ~$30-50/month

### Scaling (1000 companies)
- **VPS Cluster**: $200/month (3 servers)
- **Managed PostgreSQL**: $100/month
- **Redis Cluster**: $50/month
- **CDN**: $20/month
- **S3 Storage**: $30/month
- **Total**: ~$400/month

---

## CONCLUSION

This architecture provides:

✅ **Multi-tenancy** with proper data isolation
✅ **Provider abstraction** for easy integration of Sipuni, Binotel, and future providers
✅ **Scalable design** supporting 1000+ companies and 10K+ calls/day
✅ **Clean API structure** with `/company` endpoints
✅ **Robust authentication** with JWT and permission-based access
✅ **Complete CRM modules** (Leads, Contacts, Deals, Tasks, Notes)
✅ **Audit logging** for compliance
✅ **Soft delete** for data recovery
✅ **Localization** for Central Asia/CIS markets
✅ **Statistics & analytics** with real-time queries
✅ **Call record proxy** for security
✅ **Background jobs** for async processing
✅ **MVP-focused** with clear extension points

**Ready for 1-week implementation sprint!**
