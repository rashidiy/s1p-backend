# Owner Management Guide

**Complete Guide for SaaS Platform Administrators**

---

## Architecture Overview

Your SaaS CRM platform has a clear 3-level hierarchy:

```
Owner (Platform Admin)
  └── Company 1 (Provider: Sipuni)
       └── Users (operators, managers, admins)
  └── Company 2 (Provider: Binotel)
       └── Users (operators, managers, admins)
  └── Company 3 (Provider: Sipuni)
       └── Users (operators, managers, admins)
```

### Key Concepts

1. **Owner** = Platform administrator who manages multiple companies
2. **Company** = Tenant with its own provider configuration (Sipuni OR Binotel)
3. **Users** = Company-level users (operators, managers, admins)

---

## Owner Registration & Login

### Register as Owner

```bash
POST /api/v1/owner/auth/register
Content-Type: application/json

{
  "email": "admin@yourplatform.com",
  "password": "SecurePassword123!",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+998901234567"
}
```

**Response:**
```json
{
  "id": "uuid-here",
  "email": "admin@yourplatform.com",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+998901234567",
  "is_active": true,
  "email_verified": false,
  "created_at": "2026-01-22T...",
  "credentials": {
    "access": "eyJ...",  // JWT access token
    "refresh": "eyJ..."   // JWT refresh token
  }
}
```

### Login as Owner

```bash
POST /api/v1/owner/auth/login
Content-Type: application/json

{
  "email": "admin@yourplatform.com",
  "password": "SecurePassword123!"
}
```

**Response:** Same as registration

### Get Current Owner Profile

```bash
GET /api/v1/owner/auth/me
Authorization: Bearer YOUR_ACCESS_TOKEN
```

---

## Company Management

### Create a New Company

When creating a company, you **must select a provider** (Sipuni or Binotel) and provide the provider configuration. **The provider cannot be changed later.**

#### Example: Create Company with Sipuni

```bash
POST /api/v1/owner/companies
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json

{
  "name": "My First Company LLC",
  "provider_type": "sipuni",
  "provider_config": {
    "sipuni_user": "user@example.com",
    "sipuni_secret": "your-sipuni-secret-key"
  },
  "settings": {
    "timezone": "Asia/Tashkent",
    "language": "ru"
  }
}
```

#### Example: Create Company with Binotel

```bash
POST /api/v1/owner/companies
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json

{
  "name": "Second Company Inc",
  "provider_type": "binotel",
  "provider_config": {
    "binotel_key": "your-binotel-api-key",
    "binotel_secret": "your-binotel-secret"
  },
  "settings": {
    "timezone": "Europe/Kiev",
    "language": "uk"
  }
}
```

**Response:**
```json
{
  "id": "company-uuid",
  "name": "My First Company LLC",
  "provider_type": "sipuni",
  "is_active": true,
  "webhook_url": "https://your-domain.com/api/v1/company/webhooks/abc123...",
  "webhook_token": "abc123...",
  "provider_config": {
    "sipuni_user": "user@example.com",
    "sipuni_secret": "your-sipuni-secret-key"
  },
  "settings": {
    "timezone": "Asia/Tashkent",
    "language": "ru"
  },
  "created_at": "2026-01-22T...",
  "updated_at": "2026-01-22T..."
}
```

**⚠️ Important:** Copy the `webhook_url` and configure it in your telephony provider's settings!

### List All Your Companies

```bash
GET /api/v1/owner/companies
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Response:**
```json
[
  {
    "id": "uuid-1",
    "name": "Company 1",
    "provider_type": "sipuni",
    "is_active": true,
    "webhook_url": "https://your-domain.com/api/v1/company/webhooks/token1",
    "created_at": "2026-01-22T...",
    "updated_at": "2026-01-22T..."
  },
  {
    "id": "uuid-2",
    "name": "Company 2",
    "provider_type": "binotel",
    "is_active": true,
    "webhook_url": "https://your-domain.com/api/v1/company/webhooks/token2",
    "created_at": "2026-01-22T...",
    "updated_at": "2026-01-22T..."
  }
]
```

### Get Company Details

```bash
GET /api/v1/owner/companies/{company_id}
Authorization: Bearer YOUR_ACCESS_TOKEN
```

### Update Company

```bash
PUT /api/v1/owner/companies/{company_id}
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json

{
  "name": "New Company Name",
  "settings": {
    "timezone": "Asia/Almaty",
    "language": "kz"
  },
  "is_active": true
}
```

**Note:** You **cannot** change `provider_type` or `provider_config` after creation.

### Deactivate Company

```bash
POST /api/v1/owner/companies/{company_id}/deactivate
Authorization: Bearer YOUR_ACCESS_TOKEN
```

This suspends all access for the company and its users.

### Activate Company

```bash
POST /api/v1/owner/companies/{company_id}/activate
Authorization: Bearer YOUR_ACCESS_TOKEN
```

Restores access for the company.

### Delete Company

**Soft Delete (Recommended):**
```bash
DELETE /api/v1/owner/companies/{company_id}
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Hard Delete (Permanent):**
```bash
DELETE /api/v1/owner/companies/{company_id}?hard=true
Authorization: Bearer YOUR_ACCESS_TOKEN
```

---

## Company Operations (Provider-Agnostic)

Once a company is created, **all telephony operations use `/company/*` endpoints**, regardless of provider.

### Company User Authentication

Company users (not owners) use the regular auth endpoints:

```bash
POST /api/v1/auth/login
{
  "email": "operator@company.com",
  "password": "password"
}
```

### Make a Call (Works with Any Provider)

```bash
POST /api/v1/company/calls
Authorization: Bearer COMPANY_USER_TOKEN
Content-Type: application/json

{
  "phone_1": "+998901234567",
  "phone_2": "+998907654321"
}
```

The system automatically uses the company's configured provider (Sipuni or Binotel).

### Get Call History

```bash
GET /api/v1/company/calls
Authorization: Bearer COMPANY_USER_TOKEN
```

### Get Call Recording

```bash
GET /api/v1/company/calls/{call_id}/recording
Authorization: Bearer COMPANY_USER_TOKEN
```

Returns a secure, time-limited URL to access the recording.

---

## Webhook Configuration

### For Sipuni

In your Sipuni dashboard:
1. Go to Settings → Webhooks
2. Add webhook URL: `https://your-domain.com/api/v1/company/webhooks/YOUR_WEBHOOK_TOKEN`
3. Select all event types

### For Binotel

In your Binotel dashboard:
1. Go to Settings → API → Webhooks
2. Add webhook URL: `https://your-domain.com/api/v1/company/webhooks/YOUR_WEBHOOK_TOKEN`
3. Enable call events

---

## Clean Architecture Summary

### ❌ Old (Removed)
```
/api/v1/sipuni/call       ← Hardcoded to Sipuni only
/api/v1/binotel/call      ← Would need separate endpoints
```

### ✅ New (Current)
```
/api/v1/owner/...         ← Owner creates companies
/api/v1/company/...       ← Works with ANY provider
```

### Key Benefits

1. **Provider-Agnostic:** Switch providers without changing client code
2. **Multi-Tenant:** One platform, many companies
3. **Scalable:** Add new providers without breaking existing code
4. **Secure:** Each company has isolated data and configuration

---

## API Endpoint Summary

### Owner Operations
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/owner/auth/register` | Register as owner |
| POST | `/owner/auth/login` | Owner login |
| GET | `/owner/auth/me` | Get owner profile |
| POST | `/owner/companies` | Create company |
| GET | `/owner/companies` | List companies |
| GET | `/owner/companies/{id}` | Get company details |
| PUT | `/owner/companies/{id}` | Update company |
| DELETE | `/owner/companies/{id}` | Delete company |
| POST | `/owner/companies/{id}/activate` | Activate company |
| POST | `/owner/companies/{id}/deactivate` | Deactivate company |

### Company Operations (Provider-Agnostic)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/company/calls` | Make call (any provider) |
| GET | `/company/calls` | Get call history |
| GET | `/company/calls/{id}` | Get call details |
| GET | `/company/calls/{id}/recording` | Get recording URL |
| POST | `/company/webhooks/{token}` | Webhook handler (any provider) |

### User Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register company user |
| POST | `/auth/login` | Company user login |
| GET | `/auth/refresh` | Refresh token |

---

## Example Workflow

### 1. Owner Registers
```bash
POST /owner/auth/register
→ Receives JWT token with role=owner
```

### 2. Owner Creates Company with Sipuni
```bash
POST /owner/companies
{
  "provider_type": "sipuni",
  "provider_config": {...}
}
→ Company created, webhook token generated
```

### 3. Configure Webhook in Sipuni
```
Add webhook URL to Sipuni dashboard
```

### 4. Company Admin Logs In
```bash
POST /auth/login
→ Receives JWT with company_id and permissions
```

### 5. Make Calls
```bash
POST /company/calls
→ Automatically uses Sipuni (company's provider)
```

### 6. Receive Webhooks
```bash
Sipuni → POST /company/webhooks/{token}
→ System validates IP, processes webhook
→ Stores call event in database
```

---

## Security Features

✅ **JWT Multi-Tenant Security**
- JWT includes `company_id`, `role`, `permissions`
- Company validation on every request
- Prevents cross-company access

✅ **Webhook IP Whitelisting**
- Provider-specific IP validation
- Configurable via environment variables
- Blocks unauthorized webhook attempts

✅ **Call Recording Proxy**
- Time-limited signed tokens
- No direct provider URL exposure
- Company ownership validation

✅ **Soft Delete**
- Recoverable deletions
- Complete audit trail
- GDPR compliance support

---

## Configuration

Add to your `.env`:

```bash
# Application
BASE_URL=https://your-domain.com

# Webhook Security
WEBHOOK_IP_WHITELIST_ENABLED=true
SIPUNI_ALLOWED_IPS=185.22.61.0,185.22.61.1,185.22.61.2
BINOTEL_ALLOWED_IPS=91.205.41.0,91.205.41.1

# Recording Proxy
RECORD_PROXY_SECRET=your-secret-key-32-chars-minimum
RECORD_PROXY_TOKEN_EXPIRY=86400
```

---

## Support

For questions or issues:
1. Check this guide
2. Review API documentation: `/docs` (Swagger UI)
3. Check logs for error messages

**Status: ✅ Production Ready**
