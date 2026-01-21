# Next Steps - Database Migration & API Development

## ✅ What Was Completed

All core architecture has been implemented and pushed to branch `claude/crm-service-selection-aDYxj`.

### Commits:
1. **7ea5009** - "Implement multi-tenant CRM architecture with telephony abstraction" (21 files, 6,220+ lines)
2. **c9b6cde** - "Add missing dependencies (python-jose, aiohttp) to requirements.txt"
3. **1262215** - "Add QUICKSTART guide and .env file"

### Deliverables:
- ✅ Complete multi-tenant architecture
- ✅ 11 database models (Owner, Company, User, CallEvent, Contact, Lead, Deal, Task, Note, Tag, AuditLog)
- ✅ Telephony provider abstraction (Sipuni + Binotel)
- ✅ Permission system (4 roles, 30+ permissions)
- ✅ Comprehensive documentation (600+ lines)

---

## 🔴 Critical Next Step: Database Migration

### Issue Encountered

When trying to run Alembic, there's a missing dependency error that has been resolved:
- ✅ `python-jose` - Installed
- ✅ `aiohttp` - Installed
- ✅ All other dependencies - Installed

However, **no database migration has been created yet**. The models exist but tables don't exist in the database.

### Create Migration

```bash
# Activate virtual environment
source venv/bin/activate

# Create migration file
alembic revision -m "create_multi_tenant_schema"
```

This will create a file in `source/alembic/versions/XXXX_create_multi_tenant_schema.py`

### Migration Template

Edit the generated migration file with this structure:

```python
"""create_multi_tenant_schema

Revision ID: XXXX
Revises:
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'XXXX'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create enum types
    op.execute("""
        CREATE TYPE provider_enum AS ENUM ('sipuni', 'binotel');
        CREATE TYPE role_enum AS ENUM ('owner', 'company_admin', 'company_manager', 'company_operator');
        CREATE TYPE call_state_enum AS ENUM ('ANSWER', 'BUSY', 'NOANSWER', 'CANCEL', 'CONGESTION', 'CHANUNAVAIL');
        CREATE TYPE call_direction_enum AS ENUM ('inbound', 'outbound', 'internal');
        CREATE TYPE lead_status_enum AS ENUM ('new', 'contacted', 'qualified', 'converted', 'lost');
        CREATE TYPE pipeline_stage_enum AS ENUM ('new', 'contact_made', 'meeting_scheduled', 'proposal_sent', 'negotiation', 'won', 'lost');
        CREATE TYPE deal_stage_enum AS ENUM ('prospecting', 'qualification', 'proposal', 'negotiation', 'closed_won', 'closed_lost');
        CREATE TYPE task_status_enum AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');
        CREATE TYPE task_priority_enum AS ENUM ('low', 'medium', 'high', 'urgent');
    """)

    # 2. Create owners table
    op.create_table(
        'owners',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(225)),
        sa.Column('last_name', sa.String(225)),
        sa.Column('phone', sa.String(50)),
        sa.Column('is_active', sa.Boolean, default=False, nullable=False),
        sa.Column('is_suspended', sa.Boolean, default=False, nullable=False),
        sa.Column('email_verified', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())
    )

    # 3. Create companies table
    op.create_table(
        'companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('owners.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('subdomain', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('provider_type', sa.Enum('sipuni', 'binotel', name='provider_enum'), nullable=False, index=True),
        sa.Column('provider_config', postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('webhook_token', sa.String(64), unique=True, index=True),
        sa.Column('timezone', sa.String(50), default='Asia/Tashkent'),
        sa.Column('locale', sa.String(10), default='en'),
        sa.Column('phone', sa.String(50)),
        sa.Column('address', sa.Text),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())
    )

    # 4. Modify users table
    # (Assuming users table exists, modify it. If not, create from scratch)
    # This is complex - see ARCHITECTURE.md Section 16 for migration strategy

    # 5. Create CRM tables (contacts, leads, deals, tasks, notes, tags)
    # ... (follow structure in model files)

    # 6. Create audit_logs table
    # ... (follow structure in audit_log.py)

    # 7. Create call_events table (unified)
    # ... (follow structure in call_event.py)

    # 8. Migrate existing data
    # If you have existing Sipuni data, migrate it to companies table
    # See ARCHITECTURE.md Section 16.2 for migration script


def downgrade():
    # Drop all tables and enums in reverse order
    op.drop_table('audit_logs')
    op.drop_table('call_events')
    op.drop_table('tags')
    op.drop_table('notes')
    op.drop_table('tasks')
    op.drop_table('deals')
    op.drop_table('leads')
    op.drop_table('contacts')
    # ... etc

    op.execute("DROP TYPE IF EXISTS task_priority_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS task_status_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS deal_stage_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS pipeline_stage_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS lead_status_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS call_direction_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS call_state_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS role_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS provider_enum CASCADE")
```

### Run Migration

```bash
# Apply migration
alembic upgrade head

# Verify tables were created
psql -U sipcrm -d sipcrm -c "\dt"
```

---

## 🚀 After Migration: API Development

### Priority 1: Essential Endpoints (2-3 days)

Create these endpoint files:

#### 1. Owner Management
```python
# source/api/v1/routers/owners/__init__.py

from fastapi import APIRouter, Depends, HTTPException
from source.db.models import Owner
from source.utils.managers import JWTManager
from source.api.v1.schemas.owner import OwnerCreate, OwnerResponse

router = APIRouter()

@router.post("/register", response_model=OwnerResponse)
async def register_owner(data: OwnerCreate):
    # Create owner
    owner = await Owner.create(**data.dict())
    return owner

@router.post("/login")
async def login_owner(email: str, password: str):
    # Authenticate owner
    # Generate JWT token
    pass
```

#### 2. Company Management
```python
# source/api/v1/routers/companies/__init__.py

from fastapi import APIRouter, Depends
from source.db.models import Company, Owner
from source.utils.permissions import require_role, RoleEnum

router = APIRouter()

@router.post("/")
@require_role(RoleEnum.OWNER)
async def create_company(data: CompanyCreate, owner: Owner = Depends(Owner.current)):
    # Create company with provider config
    company = await Company.create(
        owner_id=owner.id,
        **data.dict()
    )
    return company
```

#### 3. Company Calls (Provider-Agnostic!)
```python
# source/api/v1/routers/company/calls.py

from fastapi import APIRouter, Depends
from source.db.models import User, Company
from source.utils.services.telephony import ProviderFactory, CallRequest
from source.utils.permissions import require_permissions, Permissions

router = APIRouter()

@router.post("/")
@require_permissions(Permissions.CALLS_MAKE)
async def make_call(
    request: CallRequest,
    user: User = Depends(User.current)
):
    # Get company
    company = await Company.get_or_404(id=user.company_id)

    # Create provider (automatic routing!)
    provider = ProviderFactory.create(
        company.provider_type,
        company.provider_config
    )

    # Make call
    result = await provider.make_call(request)

    # Store call event
    if result.success:
        await CallEvent.create(
            company_id=company.id,
            provider_type=company.provider_type,
            provider_call_id=result.call_id,
            phone_1=request.phone_1,
            phone_2=request.phone_2,
            operator_id=user.id
        )

    return result
```

#### 4. Unified Webhook Handler
```python
# source/api/v1/routers/company/webhooks.py

from fastapi import APIRouter, Request, HTTPException
from source.db.models import Company, CallEvent
from source.utils.services.telephony import ProviderFactory

router = APIRouter()

@router.post("/{token}")
async def handle_webhook(token: str, request: Request):
    # Get request body
    payload = await request.json() if request.headers.get('content-type') == 'application/json' else await request.form()

    # Find company by webhook token
    company = await Company.get_one(webhook_token=token)
    if not company:
        raise HTTPException(404, "Invalid webhook token")

    # Create provider instance
    provider = ProviderFactory.create(
        company.provider_type,
        company.provider_config
    )

    # Validate webhook
    if not await provider.validate_webhook_auth(dict(payload), dict(request.headers)):
        raise HTTPException(403, "Invalid webhook")

    # Handle webhook (provider-specific logic)
    call_data = await provider.handle_webhook(dict(payload), dict(request.headers))

    if not call_data:
        return {"status": "ignored"}

    # Store/update call event (same format for all providers!)
    await CallEvent.create(**call_data)

    return {"status": "success"}
```

### Priority 2: CRM Endpoints (1-2 days)

- `/api/v1/company/contacts` - Contact CRUD + import/export
- `/api/v1/company/leads` - Lead pipeline management
- `/api/v1/company/deals` - Deal tracking
- `/api/v1/company/tasks` - Task management
- `/api/v1/company/notes` - Notes system
- `/api/v1/company/tags` - Tag management

### Priority 3: Statistics (1 day)

```python
# source/api/v1/routers/company/stats.py

@router.get("/dashboard")
async def get_dashboard(user: User = Depends(User.current)):
    # Query database for stats
    total_calls_today = await CallEvent.count(
        company_id=user.company_id,
        created_at__gte=datetime.now().replace(hour=0, minute=0)
    )

    # ... more stats

    return {
        "total_calls_today": total_calls_today,
        "answered_calls_today": answered,
        "active_leads": active_leads_count,
        "revenue_this_month": revenue
    }
```

---

## 📋 Full Roadmap

### Week 1: Core Functionality
- ✅ Day 1-2: Architecture & models (DONE!)
- 🔴 Day 3: Database migration
- 🔴 Day 4: Essential endpoints (auth, companies, calls)
- 🔴 Day 5: Pydantic schemas

### Week 2: CRM Features
- 🔴 Day 6-7: CRM endpoints (contacts, leads, deals, tasks)
- 🔴 Day 8: Statistics & dashboard
- 🔴 Day 9: Testing

### Week 3: Polish & Deploy
- 🔴 Day 10: Audit logging middleware
- 🔴 Day 11: Call record proxy (Nginx)
- 🔴 Day 12: Background jobs (Celery)
- 🔴 Day 13-14: Final testing & deployment

---

## 🐛 Known Issues to Fix

1. **Config typo:** `JWT_SINGING_KEY` should be `JWT_SIGNING_KEY` in `source/core/config.py`

   ```python
   # source/core/config.py line 30
   # Change:
   SINGING_KEY = required_env('JWT_SINGING_KEY')
   # To:
   SIGNING_KEY = required_env('JWT_SIGNING_KEY')
   ```

2. **Virtual Environment:** Created at `/home/user/SIPtools/venv` with all dependencies

3. **Environment File:** `.env` file created with example values

---

## 📚 Documentation Files

- **ARCHITECTURE.md** - Complete system design (300+ lines)
- **IMPLEMENTATION_SUMMARY.md** - What's done and what's next (400+ lines)
- **QUICKSTART.md** - Getting started guide
- **NEXT_STEPS.md** - This file (migration & development guide)

---

## ✅ Summary

**What's Complete (60%):**
- ✅ Multi-tenant architecture design
- ✅ All database models
- ✅ Telephony provider abstraction
- ✅ Sipuni & Binotel providers
- ✅ Permission system
- ✅ Documentation
- ✅ Dependencies installed

**Critical Next Step:**
1. Create Alembic migration
2. Run migration to create tables
3. Build API endpoints
4. Test with real providers

**Branch:** `claude/crm-service-selection-aDYxj`
**Commits:** 3 commits pushed
**Files Changed:** 22 files, 6,600+ lines added

---

**Ready for database migration and API development!** 🚀
