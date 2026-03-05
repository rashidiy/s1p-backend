# TODO — CRM Improvements & Email Service

## 1. Fix `get_my_tasks_today` permission (trivial)

- [ ] Add `@require_permissions(Permissions.TASKS_READ)` to `get_my_tasks_today` in `source/api/v1/routers/company/tasks.py`
- No behavior change — all roles already have `TASKS_READ`

---

## 2. Operator data scoping

**Contacts** — operators can READ and CREATE, but NOT update/delete:
- [ ] In `update_contact`: block if `user.role == OPERATOR`
- [ ] In `delete_contact`: block if `user.role == OPERATOR`
- [ ] `list_contacts` and `get_contact` remain unrestricted (all company contacts visible)
- [ ] `create_contact` remains unrestricted
- [ ] `bulk_create_contacts` remains unrestricted
- [ ] `get_contact_activity` remains unrestricted

**Leads, Deals, Tasks, Notes** — operators only see records assigned to / created by them:
- [ ] Create `source/utils/operator_scope.py` with utility:
  ```python
  def apply_operator_scope(query, user, model):
      """If user is operator, filter to assigned_to=user.id or created_by=user.id"""
  ```
- [ ] Apply in `list_leads` — filter `assigned_to == user.id` for operators
- [ ] Apply in `get_lead` — 404 if not assigned to operator
- [ ] Apply in `list_deals` — filter `assigned_to == user.id`
- [ ] Apply in `get_deal` — 404 if not assigned to operator
- [ ] Apply in `list_tasks` — filter `assigned_to == user.id OR created_by == user.id`
- [ ] Apply in `get_task` — 404 if not assigned/created by operator
- [ ] Apply in `list_notes` — filter `created_by == user.id`
- [ ] Apply in `get_note` — 404 if not created by operator
- [ ] `get_my_tasks_today` — already personal, verify it filters by user
- [ ] Managers and admins see everything (no change)

---

## 3. First admin bootstrapping + password flow

### Owner creates first admin
- [ ] Create `POST /owner/companies/{company_id}/admin` endpoint in `source/api/v1/routers/owner/companies.py` (or new file)
  - Validate company belongs to owner
  - Accept: email, first_name, last_name, phone
  - Create user with `role=COMPANY_ADMIN`, full admin permissions from `ROLE_PERMISSIONS`
  - Generate temporary password
  - Send invitation email via EmailService
  - Return user response
- [ ] Add schema `CompanyAdminCreateRequest` to `source/api/v1/schemas/owner.py`

### Force password change on first login
- [ ] Add `must_change_password` Boolean field to User model (default=True for invited users)
- [ ] In auth login response: include `must_change_password` flag
- [ ] Frontend uses this to redirect to password change screen
- [ ] After password change: set `must_change_password=False`
- [ ] Generate migration for new field

### Verify reset password flow
- [ ] Confirm `POST /company/users/reset-password` exists and works (it does in users.py)
- [ ] Ensure it sets `must_change_password=False` after reset
- [ ] Ensure `POST /company/users/me/change-password` also sets `must_change_password=False`

---

## 4. Audit trail for CRM actions

### Create utility
- [ ] Create `source/utils/audit.py`:
  ```python
  async def log_action(
      session, company_id, user_id,
      action: str,           # created, updated, deleted, assigned, converted, status_changed
      entity_type: str,      # contact, lead, deal, task, note
      entity_id: UUID,
      details: dict = None   # {"field": "stage", "old": "new", "new": "won"}
  )
  ```
- [ ] Check existing `AuditLog` model schema — verify it has the right columns

### Integrate into CRM endpoints
- [ ] Contacts: create, update, delete, bulk_create
- [ ] Leads: create, update, delete, convert, assign
- [ ] Deals: create, update, delete, win, lose
- [ ] Tasks: create, update, delete, complete
- [ ] Notes: create, update, delete

### Optional: audit log endpoint
- [ ] `GET /company/audit-log` — list recent actions (admin only)
- [ ] Filter by entity_type, user_id, date range

---

## 5. Tags router

- [ ] Create `source/api/v1/routers/company/tags.py`:
  - `POST /tags` — create tag (name, color) — `TAGS_WRITE`
  - `GET /tags` — list company tags — `TAGS_READ`
  - `PUT /tags/{id}` — update tag — `TAGS_WRITE`
  - `DELETE /tags/{id}` — delete tag — `TAGS_WRITE`
  - `POST /tags/{id}/attach` — attach to entity (entity_type + entity_id) — `TAGS_WRITE`
  - `DELETE /tags/{id}/detach` — detach from entity — `TAGS_WRITE`
- [ ] Add `TAGS_READ`, `TAGS_WRITE` to `Permissions` class
- [ ] Add to role permissions: all roles get `TAGS_READ`, admin+manager get `TAGS_WRITE`
- [ ] Check `Tag` model — verify it supports entity polymorphism (or needs a join table)
- [ ] Create tag schemas in `source/api/v1/schemas/tag.py`
- [ ] Register router in `source/api/v1/routers/company/__init__.py`

---

## 6. Email service with Jinja2 templates + background tasks

### Background task infrastructure
- [ ] Choose: **FastAPI BackgroundTasks** for simple cases, but set up **ARQ** (async Redis queue) for scalable background tasks
  - ARQ uses the existing Redis instance
  - Supports retries, scheduling, cron jobs — future-proof for more background tasks
  - Create `source/utils/worker.py` — ARQ worker config
  - Create `source/utils/tasks/` — task modules folder
  - Create `source/utils/tasks/email_tasks.py` — `send_email_task(to, subject, html_body)`
- [ ] Alternative (simpler): use `fastapi.BackgroundTasks` for now, migrate to ARQ later

### Email service
- [ ] Create/update `source/utils/services/email_service.py`:
  - SMTP config from env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`
  - Use `aiosmtplib` for async sending
  - Jinja2 template rendering
- [ ] Add to `.env.copy`: SMTP env vars

### Jinja2 templates folder
- [ ] Create `source/templates/email/` directory
- [ ] Create base layout: `source/templates/email/base.html`
  - Company logo placeholder
  - Consistent header/footer
  - Responsive design (mobile-friendly)
  - Brand colors (customizable via variables)
- [ ] Create templates:
  - `source/templates/email/invitation.html` — operator/admin invitation with temp password
  - `source/templates/email/password_reset.html` — password reset link/code
  - `source/templates/email/welcome.html` — welcome after first password change
  - `source/templates/email/contract_expiry_warning.html` — contract expiring soon
  - `source/templates/email/contract_expired.html` — contract expired notification
- [ ] Template design guidelines:
  - Clean, professional look
  - S1P branding
  - CTA buttons (e.g., "Set Your Password", "Login Now")
  - Footer with company info + unsubscribe placeholder
  - Works in Gmail, Outlook, Apple Mail (table-based layout for compatibility)

### Wire up email sending
- [ ] Refactor existing `EmailService.send_operator_invitation()` to use templates + background tasks
- [ ] Add `send_admin_invitation()` for the new owner endpoint
- [ ] Add contract-related email notifications

---

## Implementation Order

1. **Email service + templates** (foundation — needed by #3)
2. **First admin bootstrapping** (#3 — unblocks company usage)
3. **Fix tasks permission** (#1 — trivial)
4. **Operator scoping** (#2 — security)
5. **Tags router** (#5 — feature)
6. **Audit trail** (#4 — accountability)

---

## Files to Create
- `source/utils/operator_scope.py`
- `source/utils/audit.py`
- `source/utils/tasks/email_tasks.py` (+ `__init__.py`)
- `source/utils/worker.py` (if ARQ)
- `source/api/v1/routers/company/tags.py`
- `source/api/v1/schemas/tag.py`
- `source/templates/email/base.html`
- `source/templates/email/invitation.html`
- `source/templates/email/password_reset.html`
- `source/templates/email/welcome.html`
- `source/templates/email/contract_expiry_warning.html`
- `source/templates/email/contract_expired.html`

## Files to Modify
- `source/api/v1/routers/company/tasks.py` (#1)
- `source/api/v1/routers/company/contacts.py` (#2)
- `source/api/v1/routers/company/leads.py` (#2)
- `source/api/v1/routers/company/deals.py` (#2)
- `source/api/v1/routers/company/notes.py` (#2)
- `source/api/v1/routers/owner/companies.py` (#3)
- `source/api/v1/schemas/owner.py` (#3)
- `source/db/models/user.py` (#3 — must_change_password field)
- `source/db/models/enums.py` (if needed)
- `source/utils/permissions.py` (#5 — TAGS_READ/WRITE)
- `source/api/v1/routers/company/__init__.py` (#5 — register tags)
- `source/utils/services/email_service.py` (#6)
- All CRM routers (#4 — audit log calls)
