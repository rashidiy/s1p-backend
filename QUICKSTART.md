# Quick Start Guide

## ✅ Dependencies Installed

All required dependencies have been installed and added to `requirements.txt`:

```bash
# Core dependencies
✅ python-jose[cryptography]==3.3.0   # JWT authentication
✅ aiohttp==3.10.11                    # Telephony provider HTTP client
✅ passlib[bcrypt]==1.7.4              # Password hashing
✅ And all other dependencies...
```

## 🚀 Getting Started

### 1. Install Dependencies

If you haven't already, create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file (or copy from `.env.copy`):

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sipcrm
POSTGRES_USER=sipcrm
POSTGRES_PASSWORD=your_secure_password

# JWT (Note: there's a typo in config.py - JWT_SINGING_KEY should be JWT_SIGNING_KEY)
JWT_ALGORITHM=HS256
JWT_SINGING_KEY=your-super-secret-jwt-key-min-32-chars-long-change-in-production

# Application
DEBUG=True
```

### 3. Set Up Database

```bash
# Start PostgreSQL (example using Docker)
docker run -d \
  --name sipcrm-postgres \
  -e POSTGRES_DB=sipcrm \
  -e POSTGRES_USER=sipcrm \
  -e POSTGRES_PASSWORD=your_secure_password \
  -p 5432:5432 \
  postgres:15-alpine

# Create database migration
alembic revision -m "initial_multi_tenant_schema"

# Edit the migration file in source/alembic/versions/
# Add code to create all tables (owners, companies, users, etc.)

# Run migration
alembic upgrade head
```

### 4. Test Imports

```bash
source venv/bin/activate

python -c "
import sys
sys.path.insert(0, 'source')

from utils.services.telephony import ProviderFactory
print('Registered providers:', ProviderFactory.list_providers())
# Should output: Registered providers: ['sipuni', 'binotel']
"
```

## 📁 Project Structure

```
SIPtools/
├── ARCHITECTURE.md              # Complete system design (READ THIS FIRST!)
├── IMPLEMENTATION_SUMMARY.md    # What's done and what's next
├── QUICKSTART.md               # This file
├── requirements.txt             # All dependencies
├── .env                        # Environment variables (create this)
├── main.py                     # FastAPI entry point
├── alembic.ini                 # Database migration config
│
└── source/
    ├── core/
    │   └── config.py           # Configuration (DATABASE, JWT)
    │
    ├── db/
    │   ├── base.py             # SQLAlchemy Base
    │   ├── models/
    │   │   ├── owner.py        # ✅ Platform accounts
    │   │   ├── company.py      # ✅ Tenants
    │   │   ├── user.py         # ✅ Company users
    │   │   ├── call_event.py   # ✅ Unified calls
    │   │   ├── contact.py      # ✅ CRM contacts
    │   │   ├── lead.py         # ✅ CRM leads
    │   │   ├── deal.py         # ✅ CRM deals
    │   │   ├── task.py         # ✅ CRM tasks
    │   │   ├── note.py         # ✅ CRM notes
    │   │   ├── tag.py          # ✅ CRM tags
    │   │   ├── audit_log.py    # ✅ Audit trail
    │   │   └── enums.py        # ✅ All enumerations
    │   │
    │   └── mixins/
    │       ├── auth_manager.py      # JWT authentication
    │       └── object_manager.py     # CRUD operations
    │
    ├── utils/
    │   ├── services/
    │   │   └── telephony/      # ✅ Provider abstraction
    │   │       ├── base.py              # Abstract interface
    │   │       ├── factory.py           # Provider factory
    │   │       ├── sipuni_provider.py   # Sipuni implementation
    │   │       └── binotel_provider.py  # Binotel implementation
    │   │
    │   ├── permissions.py      # ✅ Permission system
    │   └── managers/
    │       ├── token_manager.py     # JWT tokens
    │       └── password_manager.py  # Password hashing
    │
    └── api/v1/
        ├── routers/
        │   ├── auth/           # Existing auth endpoints
        │   ├── sipuni/         # Legacy (to be replaced)
        │   ├── owners/         # 🔴 TODO
        │   ├── companies/      # 🔴 TODO
        │   └── company/        # 🔴 TODO (main CRM endpoints)
        │
        └── schemas/            # 🔴 TODO (Pydantic schemas)
```

## 🎯 What's Complete (60%)

✅ **Architecture Design** - Complete multi-tenant CRM architecture (see ARCHITECTURE.md)
✅ **Database Models** - 11 models with relationships, soft delete, timestamps
✅ **Telephony Abstraction** - Provider-agnostic interface for Sipuni/Binotel
✅ **Sipuni Provider** - Full implementation (external call, call number, call tree)
✅ **Binotel Provider** - Ported from Django code
✅ **Permission System** - 4 roles, 30+ permissions, decorators
✅ **Documentation** - 500+ lines of comprehensive docs

## 🔴 What's Next (40%)

### Priority 1: Database Migration (1-2 hours)

```bash
# Create migration
alembic revision -m "multi_tenant_crm_schema"

# Edit the migration file to:
# 1. Create new enum types
# 2. Create owners table
# 3. Create companies table
# 4. Modify users table (add company_id, role, permissions)
# 5. Create CRM tables (contacts, leads, deals, tasks, notes, tags)
# 6. Create audit_logs table
# 7. Create call_events table (unified)
# 8. Migrate existing data from sipuni table to companies

# Run migration
alembic upgrade head
```

### Priority 2: API Endpoints (2-3 days)

**Essential endpoints:**
- `/api/v1/owners` - Owner registration & management
- `/api/v1/companies` - Company CRUD
- `/api/v1/company/calls` - Make calls (provider-agnostic!)
- `/api/v1/company/webhooks/{token}` - Unified webhook receiver
- `/api/v1/company/users` - User management

**CRM endpoints:**
- `/api/v1/company/contacts` - Contact CRUD + import/export
- `/api/v1/company/leads` - Lead pipeline
- `/api/v1/company/deals` - Deal tracking
- `/api/v1/company/tasks` - Task management
- `/api/v1/company/notes` - Notes
- `/api/v1/company/stats` - Statistics & dashboard

### Priority 3: Pydantic Schemas (1 day)

Create request/response models for all entities:
```python
# Example: source/api/v1/schemas/company/company_create.py
from pydantic import BaseModel
from source.db.models.enums import ProviderEnum

class CompanyCreate(BaseModel):
    name: str
    subdomain: str
    provider_type: ProviderEnum
    provider_config: dict
```

### Priority 4: Testing (1-2 days)

- Unit tests for providers
- Integration tests for API endpoints
- Test multi-tenant data isolation

## 💡 Usage Examples

### Making a Call (Provider-Agnostic!)

```python
from source.utils.services.telephony import ProviderFactory, CallRequest
from source.db.models import Company

# Get company (could be Sipuni or Binotel)
company = await Company.get_one(id=company_id)

# Create provider instance (automatic routing!)
provider = ProviderFactory.create(
    provider_type=company.provider_type,  # 'sipuni' or 'binotel'
    config=company.provider_config
)

# Make call (same code for both providers!)
result = await provider.make_call(
    CallRequest(
        phone_1="998901234567",
        phone_2="100"
    )
)

if result.success:
    print(f"Call initiated: {result.call_id}")
```

### Permission-Protected Endpoint

```python
from source.utils.permissions import require_permissions, Permissions
from source.db.models import Lead, User

@router.get("/leads")
@require_permissions(Permissions.LEADS_READ)
async def get_leads(user: User = Depends(User.current)):
    # Only users with 'leads.read' permission can access
    leads = await Lead.get_all(
        company_id=user.company_id,
        deleted_at=None  # Soft delete filter
    )
    return leads
```

### Handling Provider Webhook (Unified)

```python
@router.post("/company/webhooks/{token}")
async def handle_webhook(token: str, payload: Dict, request: Request):
    # 1. Find company by webhook token
    company = await Company.get_one(webhook_token=token)

    # 2. Create provider instance
    provider = ProviderFactory.create(
        company.provider_type,
        company.provider_config
    )

    # 3. Validate webhook
    if not await provider.validate_webhook_auth(payload, dict(request.headers)):
        raise HTTPException(403, "Invalid webhook")

    # 4. Handle webhook (provider normalizes data)
    call_data = await provider.handle_webhook(payload, dict(request.headers))

    # 5. Store call event (same format for all providers!)
    await CallEvent.create(company_id=company.id, **call_data)

    return {"status": "success"}
```

## 🐛 Known Issues

1. **Config typo:** `JWT_SINGING_KEY` should be `JWT_SIGNING_KEY` in `source/core/config.py`
2. **No database migration yet** - Tables don't exist in database
3. **No API endpoints yet** - Only models exist, controllers need to be built
4. **Import circular dependency** - Models might have circular import issues (need testing)

## 📚 Documentation

- **ARCHITECTURE.md** - Complete system architecture (300+ lines)
  - Multi-tenant design
  - Database schema with ER diagrams
  - Telephony abstraction
  - API routing structure
  - Statistics & analytics
  - Call records proxy (Nginx)
  - Background jobs
  - Deployment guidelines

- **IMPLEMENTATION_SUMMARY.md** - Implementation status
  - What's complete
  - What's next
  - Usage examples
  - File structure
  - Development roadmap

## 🚀 Running the Application

Once database is migrated and endpoints are built:

```bash
# Development server
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production server
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

Access API docs at: http://localhost:8000/

## 📞 Support

For detailed information, see:
1. **ARCHITECTURE.md** - System design
2. **IMPLEMENTATION_SUMMARY.md** - Implementation status
3. Model files - Inline documentation
4. Telephony providers - Usage examples in docstrings

---

**Status:** Core architecture complete (60%), ready for database migration and API development.
