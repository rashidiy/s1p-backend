# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SIPtools is a multi-tenant call center CRM platform built with FastAPI. It provides a unified API for telephony providers (Sipuni and Binotel) with integrated CRM capabilities (contacts, leads, deals, tasks, notes). The platform uses an Owner → Company → User hierarchy where each company configures one telephony provider.

## Commands

### Local Development
```bash
make run              # Start FastAPI dev server (uvicorn --reload on port 8000)
make mig              # Create autogenerate migration + apply (alembic revision --autogenerate + upgrade head)
make test             # Run pytest (python -m pytest tests/ -v --tb=short)
```

### Docker
```bash
make build            # Build Docker images
make up               # Start app + db + redis
make dev              # Start with dev tools (pgadmin on :5050, redis-commander on :8081)
make down             # Stop services
make logs             # Follow app logs
make db-migrate       # Run migrations inside container
make db-shell         # PostgreSQL CLI in container
make redis-shell      # Redis CLI in container
```

### Single Test
```bash
python -m pytest tests/path/to/test_file.py::test_function -v
```

## Architecture

### Source Layout
All application code lives under `source/` (added to `sys.path` in `main.py`). Imports within source use bare module paths (e.g., `from core.config import DatabaseConfig`, not `from source.core.config`).

- `source/core/config.py` — Environment-based configuration classes (DatabaseConfig, JWTConfig, WebhookConfig)
- `source/db/base.py` — SQLAlchemy async engine, Base class, and `get_session` dependency
- `source/db/models/` — 15 SQLAlchemy models, all multi-tenant with `company_id` FK
- `source/db/models/enums.py` — All enum types (roles, call states, lead/deal stages, etc.)
- `source/db/mixins/` — `ObjectManagerMixin` (generic CRUD), `AuthenticationManagerMixin` (JWT auth)
- `source/api/v1/routers/` — Three router groups: `auth/`, `owner/`, `company/` (mounted at `/api/v1`)
- `source/api/v1/schemas/` — Pydantic v2 request/response models
- `source/utils/services/telephony/` — Provider abstraction layer (Strategy + Factory pattern)
- `source/utils/managers/` — Token, password, and recording proxy managers
- `source/utils/permissions.py` — Role-based access control with `@require_permissions` decorator
- `source/alembic/` — Async Alembic migration env (`env.py` overrides URL from DatabaseConfig)

### Key Patterns

**Multi-tenancy:** Every CRM table has `company_id`. All queries must filter by `company_id` from the authenticated user's JWT. The JWT payload includes `sub` (user ID), `company_id`, `role`, and `permissions`.

**Telephony provider abstraction:** `TelephonyProvider` abstract base class in `source/utils/services/telephony/base.py` with `SipuniProvider` and `BinotelProvider` implementations. `ProviderFactory.create(provider_type, config)` returns the correct provider. Endpoints are provider-agnostic — the company's `provider_type` and `provider_config` (JSONB) determine routing.

**Model mixins:** Models inherit from `Base` + `ObjectManagerMixin` to get `create()`, `get()`, `get_all()`, `update()`, `delete()`, `get_or_create()` as async class methods. Auth models also use `AuthenticationManagerMixin` for `User.current()` dependency.

**Permission system:** Roles are `OWNER`, `COMPANY_ADMIN`, `COMPANY_MANAGER`, `COMPANY_OPERATOR`. Permissions are granular (e.g., `leads.read`, `calls.make`). Applied via `@require_permissions(Permissions.LEADS_READ)` decorator on endpoints.

### Database

PostgreSQL 16 with async driver (asyncpg). Alembic migrations in `source/alembic/versions/`. The `alembic.ini` sets `prepend_sys_path = source` so migrations can import models. `docker-entrypoint.sh` runs `alembic upgrade head` on container start when `RUN_MIGRATIONS=true`.

### Environment

Required env vars (loaded from `.env` via python-dotenv): `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `JWT_SIGNING_KEY`. See `.env.copy` for template.

### API Docs

Swagger UI is served at `/` (root URL) with `persistAuthorization` enabled.

### Tech Stack

Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, asyncpg, Alembic, Redis (caching), httpx (async HTTP), python-jose (JWT), passlib+bcrypt (passwords).