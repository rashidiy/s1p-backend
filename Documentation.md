# SIPtools — Project Documentation for AI Agents

This document consolidates project knowledge for AI agents working in any branch.

## What This Project Is

Multi-tenant call center CRM platform (FastAPI + PostgreSQL). Integrates Sipuni and Binotel telephony providers behind a unified API. Hierarchy: **Owner → Company → User**. Each company configures exactly one provider (immutable after creation).

Target scale: 1,000+ companies, ~20 users/company, ~150 calls/day/company.

## Database Schema

All primary keys are UUIDs (`gen_random_uuid()`). All CRM entities use soft delete (`deleted_at`). All tenant-scoped tables have `company_id` FK.

### Enums

| Enum | Values |
|------|--------|
| `ProviderEnum` | `sipuni`, `binotel` |
| `RoleEnum` | `owner`, `company_admin`, `company_manager`, `company_operator` |
| `CallStatusEnum` | `ANSWER`, `BUSY`, `NOANSWER`, `CANCEL`, `CONGESTION`, `CHANUNAVAIL` |
| `CallDirectionEnum` | `inbound`, `outbound`, `internal` |
| `CallOutcomeEnum` | `interested`, `appointment_scheduled`, `follow_up`, `sale_made`, `no_answer`, `left_voicemail`, `busy`, `callback_requested`, `information_provided`, `not_interested`, `wrong_number`, `do_not_call`, `customer_complaint`, `other` |
| `LeadStatusEnum` | `new`, `contacted`, `qualified`, `converted`, `lost` |
| `PipelineStageEnum` | `new`, `contact_made`, `meeting_scheduled`, `proposal_sent`, `negotiation`, `won`, `lost` |
| `DealStageEnum` | `prospecting`, `qualification`, `proposal`, `negotiation`, `closed_won`, `closed_lost` |
| `TaskStatusEnum` | `pending`, `in_progress`, `completed`, `cancelled` |
| `TaskPriorityEnum` | `low`, `medium`, `high`, `urgent` |

### Models

**owners** — Platform master accounts. Fields: `id`, `email` (unique), `password_hash`, `first_name`, `last_name`, `phone`, `is_active`, `is_suspended`, `email_verified`, timestamps. Relationship: `companies` (1:N cascade).

**companies** — Tenant entity. Fields: `id`, `owner_id` (FK), `name`, `subdomain` (unique), `provider_type` (ProviderEnum, immutable), `provider_config` (JSONB), `webhook_token` (unique, auto-generated via `secrets.token_urlsafe(32)`), `timezone` (default "Asia/Tashkent"), `locale`, `phone`, `address`, `is_active`, `deleted_at`, timestamps. Relationships: owner, users, call_events, contacts, leads, deals, tasks, notes, tags, audit_logs.

**users** — Company users. Fields: `id`, `company_id` (FK), `first_name`, `last_name`, `email`, `phone`, `password_hash`, `role` (RoleEnum), `permissions` (JSONB array), `language`, `is_active`, `is_suspended`, `email_verified`, `deleted_at`, timestamps. UniqueConstraint: (`company_id`, `email`).

**call_events** — Unified call tracking. Fields: `id`, `company_id` (FK), `provider_type`, `provider_call_id`, `phone_1` (caller), `phone_2` (receiver), `operator_id` (FK to users), `direction`, `state`, `outcome`, `disposition_notes`, `attempts`, `waiting_sec`, `billing_sec`, `record_url`, `call_start_timestamp`, `call_end_timestamp`, `contact_id` (FK), `lead_id` (FK), `deal_id` (FK), `utm_source`, `utm_medium`, `utm_campaign`, `company_number`, `order_id`, timestamps. UniqueConstraint: (`company_id`, `provider_type`, `provider_call_id`).

**contacts** — Fields: `id`, `company_id`, `first_name`, `last_name`, `company_name`, `phone` (indexed), `email` (indexed), `position`, `source`, `tags` (JSONB), `custom_fields` (JSONB), `created_by` (FK), `assigned_to` (FK), `deleted_at`, timestamps.

**leads** — Fields: `id`, `company_id`, `contact_id` (FK), `title`, `description`, `source`, `status` (LeadStatusEnum), `pipeline_stage` (PipelineStageEnum), `estimated_value` (Numeric(15,2)), `currency`, `assigned_to` (FK), `tags` (JSONB), `custom_fields` (JSONB), `deleted_at`, timestamps. Method: `convert_to_deal()`.

**deals** — Fields: `id`, `company_id`, `lead_id` (FK), `contact_id` (FK), `title`, `description`, `amount` (Numeric(15,2)), `currency`, `stage` (DealStageEnum), `probability` (0-100), `expected_close_date`, `closed_date`, `assigned_to` (FK), `tags` (JSONB), `custom_fields` (JSONB), `deleted_at`, timestamps. Properties: `is_won`, `is_lost`, `is_closed`.

**tasks** — Polymorphic entity linking via `entity_type` + `entity_id`. Fields: `id`, `company_id`, `title`, `description`, `status`, `priority`, `due_date`, `completed_at`, `assigned_to` (FK), `created_by` (FK), `entity_type` (string), `entity_id` (UUID), `deleted_at`, timestamps.

**notes** — Polymorphic. Fields: `id`, `company_id`, `content`, `entity_type`, `entity_id`, `created_by` (FK), `deleted_at`, timestamps.

**tags** — Fields: `id`, `company_id`, `name`, `color` (default '#3B82F6'). UniqueConstraint: (`company_id`, `name`).

**audit_logs** — Fields: `id`, `company_id`, `user_id` (FK), `action`, `entity_type`, `entity_id`, `before` (JSONB), `after` (JSONB), `ip_address`, `user_agent`, `created_at`.

## API Endpoints

Swagger UI at `/swagger?type=owner` and `/swagger?type=company`. Root `/` redirects to owner swagger.

### Owner Endpoints (`/api/v1/owner/`)

**Auth** (`/auth`):
- `POST /login` — Owner login, returns JWT
- `GET /me` — Current owner profile

Owner creation is CLI-only via `python manage.py createsuperuser`. No registration endpoint.

**Companies** (`/companies`):
- `POST /` — Create company (provider_type + provider_config required; generates webhook_token)
- `GET /` — List owner's companies
- `GET /{id}` — Company details
- `PUT /{id}` — Update (name, settings, is_active — NOT provider)
- `DELETE /{id}` — Delete (`?hard=true` for permanent)
- `POST /{id}/activate` — Activate company
- `POST /{id}/deactivate` — Suspend company

**Analytics** — Platform-wide stats for owner

### Company Endpoints (`/api/v1/company/`)

All require user JWT with `company_id`.

**Calls** (`/calls`): `POST /` make call, `GET /` list, `GET /{id}` detail, `GET /{id}/recording` proxied recording URL

**Enhanced Calls** (`/calls_enhanced`): Call outcomes and CRM linking

**Webhooks** (`/webhooks`): `POST /{token}` — Unified receiver for all providers. Returns 200 even on errors to prevent retries.

**Recordings**: `/proxy/{token}` redirect, `/stream/{token}` direct stream

**Users**: Full CRUD with role/permission management

**CRM Modules** (contacts, leads, deals, tasks, notes): Full CRUD plus:
- Leads: `POST /{id}/convert` (to deal), `POST /{id}/assign`
- Deals: `POST /{id}/win`, `POST /{id}/lose`, `GET /pipeline/summary`
- Tasks: `POST /{id}/complete`, `GET /my-today`
- Notes: `GET /timeline/{type}/{id}`
- Contacts: `GET /{id}/activity`

**Analytics**: Company-level statistics

### Auth Endpoints (`/api/v1/auth/`)

Company-level user authentication: login, token refresh, verification.

## Telephony Provider Integration

### Abstract Interface (`source/utils/services/telephony/base.py`)

5 abstract methods: `make_call()`, `get_call_status()`, `get_call_record_url()`, `handle_webhook()`, `validate_webhook_auth()`. Optional: `get_call_history()`.

Factory pattern: `ProviderFactory.create(provider_type, config)`.

### Sipuni

Config: `{"cabinet_id": "...", "security_key": "...", "token": "..."}`

API base: `https://sipuni.com`. Auth: MD5 hash of params joined with `+` plus security_key (parameter order matters per endpoint).

Call endpoints: `/api/callback/call_external`, `/api/callback/call_number`, `/api/callback/call_tree`.

Webhook: Only processes hangup events (`event == 2`). Direction: `src_type=1` (external) → inbound if to internal, `src_type=2` (internal) → outbound.

### Binotel

Config: `{"cabinet_id": "...", "security_key": "...", "company_number": "100"}`

API base: `https://api.binotel.com`. Auth: `key` + `secret` in JSON POST body.

Call endpoint: `/api/4.0/calls/external-number-to-external-number.json`.

Webhook: Processes `requestType == "apiCallCompleted"`. Handles both bracket-notation form data (`callDetails[fieldName]`) AND nested JSON — Binotel may send either format.

Recording CDN: `cdn0993.s3.eu-west-1.amazonaws.com`.

## Permission System (`source/utils/permissions.py`)

### Permissions (30+)

leads.read/write/delete/assign, contacts.read/write/delete/import/export, deals.read/write/delete/assign, tasks.read/write/delete/assign, calls.read/write/make, notes.read/write/delete, users.read/create/update/write/delete/manage, stats.read/export, settings.read/manage, company.read/manage/delete

### Role Matrix

- **OWNER**: `["*"]` wildcard — bypasses all checks
- **COMPANY_ADMIN**: Everything except `company.delete`
- **COMPANY_MANAGER**: Read most, write leads/contacts/deals/tasks/notes/calls, assign leads/deals/tasks. No delete, no user management, no settings
- **COMPANY_OPERATOR**: Read-only CRM, read/write/make calls, own tasks and notes only

### Decorators

`@require_permissions("leads.read")` — checks user's permissions JSONB. Owners bypass.
`@require_role(RoleEnum.OWNER)` — checks user's role.

## Security

### JWT Structure

Owner: `{sub, type: "owner", owner_id, email, exp}`
User: `{sub, type: "user", role, owner_id, company_id, permissions, exp}`

Dual auth: `Owner.current()` for owner endpoints, `User.current()` for company endpoints.

### Webhook Security

IP whitelisting via `WEBHOOK_IP_WHITELIST_ENABLED`, `SIPUNI_ALLOWED_IPS`, `BINOTEL_ALLOWED_IPS`. Disabled by default in dev.

### Recording Proxy

HMAC-SHA256 signed tokens: `Base64(call_id:company_id:exp_timestamp:signature)`. Validates company ownership. Configurable via `RECORD_PROXY_SECRET` and `RECORD_PROXY_TOKEN_EXPIRY`.

## Important Gotchas

1. **Provider type is immutable** — cannot change after company creation. Two providers = two companies.
2. **Webhook returns 200 on errors** — prevents provider retries. Errors are logged only.
3. **Sipuni processes only hangup events** (`event == 2`), ignores others.
4. **Binotel sends dual payload formats** — bracket-notation form data OR nested JSON. Both must be handled.
5. **Sipuni MD5 hash parameter order matters** and differs per endpoint.
6. **Operators** can only update/complete their OWN tasks and notes.
7. **Lead conversion** (`POST /leads/{id}/convert?create_deal=true`) sets status to CONVERTED, pipeline_stage to WON, and auto-creates a Deal.
8. **`sys.path.append('source')`** in `main.py` — all imports use paths relative to `source/` (e.g., `from db.models.company import Company`).
9. **Soft delete** is enforced at ORM level in `ObjectManagerMixin`. Use `include_deleted=True` to query deleted records, `hard=True` to permanently delete.

## Not Yet Implemented

- Background jobs (Celery/Redis for stats aggregation, task reminders, email notifications)
- Email sending (SMTP/templates)
- File upload handling
- WebSocket real-time notifications
- Redis query caching (Redis available but not integrated for caching)
- Rate limiting
- Test suite (fixtures exist in `source/tests/conftest.py`, no test cases written)
- PostgreSQL Row-Level Security (RLS)
- Nginx config for recording proxy
- CSV import/export for contacts
- Localization system
