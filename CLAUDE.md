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
make build-no-cache   # Build without cache
make up               # Start app + db + redis
make dev              # Start with dev tools (pgadmin on :5050, redis-commander on :8081)
make down             # Stop services
make dev-down         # Stop dev services
make prod             # Start production profile
make logs             # Follow app logs
make logs-all         # Follow all service logs
make logs-db          # Follow database logs
make logs-redis       # Follow Redis logs
make db-migrate       # Run migrations inside container
make db-migrate-create msg="..."  # Create named migration
make db-downgrade     # Downgrade last migration
make db-reset         # Reset database (with safety prompt)
make db-shell         # PostgreSQL CLI in container
make redis-shell      # Redis CLI in container
make health           # Check service health
make ps               # Show running containers
make stats            # Show container resource usage
make clean-all        # Remove all containers, volumes, images
make prune            # Docker system prune
```

### Management Commands (run via Docker)
```bash
make createsuperuser              # Interactive: create a new owner account
make listowners                   # List all owners
make changepassword email=x@y.z  # Change an owner's password
```

Owners can only be created via CLI (`manage.py`). There is no registration endpoint.

### Single Test
```bash
python -m pytest tests/path/to/test_file.py::test_function -v
```

## Architecture

### Source Layout
All application code lives under `source/` (added to `sys.path` in `main.py`). Imports within source use bare module paths (e.g., `from core.config import DatabaseConfig`, not `from source.core.config`).

- `source/core/config.py` — Environment-based configuration classes (DatabaseConfig, JWTConfig, WebhookConfig)
- `source/db/base.py` — SQLAlchemy async engine, Base class, and `get_session` dependency
- `source/db/models/` — 16+ SQLAlchemy models, all multi-tenant with `company_id` FK (includes legacy `Sipuni`/`SipuniCallEvent` in `sipuni.py`)
- `source/db/models/enums.py` — All enum types (roles, call states, lead/deal stages, call outcomes, contract status, billing period, payment status, pipeline stages)
- `source/db/mixins/` — `ObjectManagerMixin` (generic CRUD), `AuthenticationManagerMixin` (JWT auth)
- `source/api/v1/routers/` — Three router groups: `auth/`, `owner/`, `company/` (mounted at `/api/v1`)
  - `company/calls/` — Provider-namespaced sub-package: `common.py`, `sipuni.py`, `binotel.py`
  - `company/calls_enhanced.py` — Call outcomes, CRM linking, auto-link suggestions
  - `company/analytics.py` — Operator/team dashboards, cache management
  - `company/recordings.py` — Authenticated call recording streaming via `aiohttp`
  - `company/webhooks.py` — Unified webhook handler (GET, with IP whitelisting)
  - `company/contract.py` — Company-facing contract view
  - `company/permission_groups.py` — Permission group management
  - `owner/contracts.py`, `owner/analytics.py`, `owner/permissions.py` — Owner-level management
- `source/api/v1/schemas/` — Pydantic v2 request/response models
- `source/utils/services/telephony/` — Provider abstraction layer (Strategy + Factory pattern)
  - `http_client.py` — `HTTPClientPool` singleton (aiohttp connection pooling, retry, DNS caching)
- `source/utils/services/analytics_service.py` — `AnalyticsService` (SQL-aggregated stats, trends, pipeline health)
- `source/utils/services/cache_service.py` — `CacheService` singleton with Redis/in-memory auto-detection, `@cached` decorator
- `source/utils/services/email_service.py` — `EmailService` facade for background email tasks
- `source/utils/services/sipuni/api_simulator.py` — Sipuni API simulator for testing
- `source/utils/managers/` — Token and password managers
- `source/utils/contract_enforcement.py` — Contract-based access control and user limits
- `source/utils/validators/phone_number_validator.py` — Uzbek phone number validation (998xx format)
- `source/utils/tasks/email_tasks.py` — Background email task functions
- `source/utils/permissions.py` — Role-based access control with `@require_permissions` decorator
- `source/alembic/` — Async Alembic migration env (`env.py` overrides URL from DatabaseConfig)
- `source/tests/integration/` — Integration tests (e.g., `test_sipuni_integration.py`, requires env vars to run)

### Key Patterns

**Multi-tenancy:** Every CRM table has `company_id`. All queries must filter by `company_id` from the authenticated user's JWT. The JWT payload includes `sub` (user ID), `company_id`, `role`, and `permissions`.

**Telephony provider abstraction:** `TelephonyProvider` abstract base class in `source/utils/services/telephony/base.py` with `SipuniProvider` and `BinotelProvider` implementations. `ProviderFactory.create(provider_type, config)` returns the correct provider. Common endpoints are provider-agnostic; provider-specific endpoints (e.g., `call_number`, `call_tree`, `cancel_call` for Sipuni) are namespaced under `calls/sipuni/` and `calls/binotel/`. The company's `provider_type` and `provider_config` (JSONB) determine routing.

**Call recordings:** Authenticated streaming via `GET /recordings/{call_id}`. The backend fetches the recording from the provider's URL using `HTTPClientPool` (aiohttp connection pool) and streams it directly to the client. Provider URLs are never exposed. Replaced the earlier token-based proxy approach.

**Webhook handling:** Unified `GET /webhooks/{token}` endpoint with IP whitelisting (`WEBHOOK_IP_WHITELIST_ENABLED`, `SIPUNI_ALLOWED_IPS`, `BINOTEL_ALLOWED_IPS`). Sipuni webhooks use GET params; only hangup events (`event == 2`) are processed.

**CallEvent IDs:** `CallEvent.id` is Integer (not UUID), using company-scoped sequential numbering via `next_call_number()` helper. The `provider_call_id` field is prefixed with the provider name (e.g., `sipuni_<id>`).

**Model mixins:** Models inherit from `Base` + `ObjectManagerMixin` to get `create()`, `get()`, `get_all()`, `update()`, `delete()`, `get_or_create()` as async class methods. Auth models also use `AuthenticationManagerMixin` for `User.current()` dependency.

**Permission system:** Roles are `OWNER`, `COMPANY_ADMIN`, `COMPANY_MANAGER`, `COMPANY_OPERATOR`. Permissions are granular (e.g., `leads.read`, `calls.make`). Applied via `@require_permissions(Permissions.LEADS_READ)` decorator on endpoints.

### Database

PostgreSQL 16 with async driver (asyncpg). Alembic migrations in `source/alembic/versions/`. The `alembic.ini` sets `prepend_sys_path = source` so migrations can import models. `docker-entrypoint.sh` runs `alembic upgrade head` on container start when `RUN_MIGRATIONS=true`.

### Environment

Required env vars (loaded from `.env` via python-dotenv): `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `JWT_SIGNING_KEY`, `REDIS_URL`. Optional: `WEBHOOK_IP_WHITELIST_ENABLED`, `SIPUNI_ALLOWED_IPS`, `BINOTEL_ALLOWED_IPS`, `BASE_URL`, `JWT_ALGORITHM`, `RECORD_PROXY_SECRET`, `RECORD_PROXY_TOKEN_EXPIRY`. See `.env.copy` for template.

### API Docs

Swagger UI is split by audience at `/swagger`:
- `/swagger?type=owner` — Owner endpoints (`/api/v1/owner/*`)
- `/swagger?type=company` — Company user endpoints (`/api/v1/auth/*` + `/api/v1/company/*`)

`/` redirects to `/swagger?type=owner`. Filtered OpenAPI schemas served at `/openapi.json?type=owner|company`.

### Docker Setup

The project root is mounted into the container (`.:/app`), so code changes trigger uvicorn's `--reload`. Uses `docker compose` v2 (not the legacy `docker-compose` v1). The Dockerfile copies all files but the volume mount overrides them in dev.

### CORS

CORS middleware is configured in `main.py` with `allow_origin_regex=r"https?://[\w-]+\.(siptools\.com|localhost)(:\d+)?"`. Credentials, all methods, and all headers are allowed.

### Tech Stack

Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, asyncpg, Alembic, Redis (caching via `CacheService`), aiohttp (async HTTP + connection pooling via `HTTPClientPool`), python-jose (JWT), passlib+bcrypt (passwords).