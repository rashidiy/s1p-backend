# S1P — CRM Backend for Call Centers

Multi-tenant CRM backend with telephony integration. Manages leads, deals, contacts, calls, and team operations for call centers. Each company gets an isolated tenant with its own subdomain, users, and telephony provider.

Live at [s1p.uz](https://s1p.uz)

<p align="center">
  <img src="docs/swagger.jpg" alt="S1P API Documentation" width="800">
</p>

---

## Features

- **Multi-tenant architecture** — Subdomain-based isolation. Owner panel manages all tenants, each company operates independently.
- **Telephony integration** — Pluggable provider system (Sipuni, Binotel). Inbound/outbound calls, recording, webhook processing, call history.
- **CRM pipeline** — Leads, deals, contacts, tasks, notes, custom fields (JSONB), tags.
- **Telegram bot** — Real-time call notifications, contact search, daily digest, missed call escalation. Mini App support. Trilingual (en/ru/uz).
- **Permission system** — Role-based access with configurable permission groups per company.
- **Public API** — External integrations for leads, contacts, deals, calls, recordings.
- **Outbound webhooks** — Push events to external systems on CRM actions.
- **Contract enforcement** — License management with expiry warnings and automated email notifications.
- **Audit logging** — Track who changed what and when.

## Tech Stack

- [FastAPI](https://fastapi.tiangolo.com/) — Async Python web framework. Chosen for native async support and automatic OpenAPI docs.
- [PostgreSQL](https://postgresql.org/) — Primary database. JSONB for custom fields, async via asyncpg.
- [SQLAlchemy 2](https://sqlalchemy.org/) — Async ORM with Alembic migrations.
- [Redis](https://redis.io/) — Caching, rate limiting, session data.
- [aiogram](https://aiogram.dev/) — Telegram bot framework with webhook mode and i18n.
- [Docker](https://docker.com/) — Containerized deployment with production and development compose files.

## Architecture

```
                    ┌──────────────────────────────────────┐
                    │           Nginx / Traefik            │
                    │  *.s1p.uz → subdomain-based routing  │
                    └──────────┬───────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐
     │  Owner API    │ │ Company API  │ │  Public API  │
     │  /api/v1/owner│ │ /api/v1/     │ │ /api/public/ │
     │               │ │  company/    │ │    v1/       │
     │ Platform admin│ │ Tenant CRM   │ │ External     │
     │ Manage tenants│ │ Leads, deals │ │ integrations │
     └───────────────┘ │ calls, tasks │ └──────────────┘
                       └──────┬───────┘
                              │
         ┌────────────────────┼─────────────────────┐
         │                    │                     │
  ┌──────▼───────┐    ┌──────▼───────┐    ┌────────▼────────┐
  │  PostgreSQL  │    │    Redis     │    │ Telephony       │
  │  21 models   │    │  Cache, rate │    │ Provider Layer  │
  │  JSONB custom│    │  limiting    │    │                 │
  │  fields      │    └──────────────┘    │ ┌─────────────┐ │
  └──────────────┘                        │ │   Sipuni    │ │
         │                                │ ├─────────────┤ │
  ┌──────▼───────┐                        │ │   Binotel   │ │
  │   Alembic    │                        │ ├─────────────┤ │
  │  Migrations  │                        │ │  (add new)  │ │
  └──────────────┘                        │ └─────────────┘ │
                                          └─────────────────┘
         ┌──────────────┐    ┌──────────────────┐
         │ Telegram Bot │    │ Background Tasks  │
         │ Notifications│    │ Daily digest      │
         │ Mini App     │    │ Missed call alert │
         │ /search      │    │ Orphan cleanup    │
         │ /today       │    │ Email tasks       │
         └──────────────┘    └──────────────────┘
```

**Key design decisions:**

- **Telephony as a pluggable layer** — Abstract base class defines the interface (`make_call`, `get_call_status`, `handle_webhook`). Factory pattern instantiates the right provider per company. Adding a new provider means implementing one class — zero changes to CRM logic.
- **Three separate API scopes** — Owner (platform), Company (tenant), Public (external). Each has its own Swagger docs at `/swagger?type=owner|company|public`.
- **Subdomain-based tenancy** — Company resolved from `X-Subdomain` header. No shared state between tenants.
- **Background schedulers** — Telegram daily digest, missed call escalation, orphan call cleanup run as async tasks within the same process. No separate Celery worker needed.

## Project Structure

```
source/
├── api/v1/
│   ├── routers/
│   │   ├── auth/          # JWT auth, Telegram auth, Mini App auth
│   │   ├── company/       # Tenant-level CRM endpoints
│   │   │   ├── leads.py, deals.py, contacts.py, tasks.py
│   │   │   ├── calls/     # Sipuni + Binotel call routes
│   │   │   ├── telegram.py, telegram_webhook.py
│   │   │   ├── custom_fields.py, permission_groups.py
│   │   │   └── webhooks.py, outbound_webhooks.py
│   │   ├── owner/         # Platform admin endpoints
│   │   └── public/        # External API
│   ├── schemas/           # Pydantic request/response models
│   └── services/          # Business logic layer
├── db/
│   ├── models/            # 21 SQLAlchemy models
│   └── mixins/            # Auth manager, object manager
├── utils/
│   ├── services/
│   │   ├── telephony/     # Provider abstraction (base, factory, sipuni, binotel)
│   │   ├── telegram_service.py, telegram_i18n.py
│   │   ├── email_service.py, cache_service.py
│   │   └── analytics_service.py
│   ├── tasks/             # Background schedulers
│   └── validators/        # Phone numbers, custom fields
├── locale/                # i18n (en, ru, uz)
├── templates/email/       # HTML email templates
└── tests/                 # 37 test files
```

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis

### With Docker

```bash
git clone https://github.com/rashidiy/s1p-backend.git
cd s1p-backend
cp .env.example .env
# Fill in POSTGRES_PASSWORD and JWT_SIGNING_KEY at minimum
docker compose up -d
```

### Manual Setup

```bash
git clone https://github.com/rashidiy/s1p-backend.git
cd s1p-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in database credentials and JWT key
alembic upgrade head
uvicorn main:app --reload
```

API docs at `http://localhost:8000/swagger`

### Running Tests

```bash
pytest
```

## API Overview

| Scope | Base Path | Purpose |
|-------|-----------|---------|
| Owner | `/api/v1/owner/` | Platform administration — manage companies, contracts, permissions |
| Company | `/api/v1/company/` | Tenant CRM — leads, deals, contacts, calls, tasks, analytics |
| Auth | `/api/v1/auth/` | JWT login, Telegram auth, Mini App auth |
| Public | `/api/public/v1/` | External integrations — create leads, push contacts, query calls |

Interactive docs: `/swagger?type=owner`, `/swagger?type=company`, `/swagger?type=public`

## License

MIT
