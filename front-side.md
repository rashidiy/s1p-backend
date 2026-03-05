# S1P CRM — Frontend Development Guide

This document provides everything needed to build a React frontend for the S1P multi-tenant call center CRM platform. It covers architecture, Docker setup, authentication flows, API specifications, data schemas, and UX guidance.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Docker Compose Setup](#2-docker-compose-setup)
3. [Authentication & Authorization](#3-authentication--authorization)
4. [API Endpoints — Company API](#4-api-endpoints--company-api)
5. [API Endpoints — Owner API](#5-api-endpoints--owner-api)
6. [Enums & Dropdown Values](#6-enums--dropdown-values)
7. [Data Schemas Reference](#7-data-schemas-reference)
8. [Permission System](#8-permission-system)
9. [UX Guidelines](#9-ux-guidelines)

---

## 1. Architecture Overview

S1P is a **multi-tenant call center CRM** with a three-level hierarchy:

```
Owner (platform admin)
  └── Company (tenant)
        ├── Admin (company_admin)
        ├── Manager (company_manager)
        └── Operator (company_operator)
```

### Two Separate Frontends

The platform requires **two separate React applications** served on different subdomains:

| App | Subdomain | Purpose | API Base |
|-----|-----------|---------|----------|
| **Owner Panel** | `owners.localhost:3000` | Platform administration — manage companies, contracts, invite admins | `/api/v1/owner/*` |
| **Company Panel** | `<company>.localhost:3000` | CRM workspace — calls, contacts, leads, deals, tasks | `/api/v1/auth/*` + `/api/v1/company/*` |

### Backend API

- **Base URL:** `http://localhost:8000`
- **API prefix:** `/api/v1`
- **Swagger docs:** `http://localhost:8000/swagger?type=owner` and `http://localhost:8000/swagger?type=company`

The backend identifies the company by the **Origin header** — the frontend subdomain determines which company the user belongs to.

---

## 2. Docker Compose Setup

### Frontend Docker Compose

Create a `docker-compose.frontend.yml` (or extend the existing one) that runs both frontends with subdomain routing:

```yaml
services:
  # Nginx reverse proxy for subdomain routing
  nginx:
    image: nginx:alpine
    container_name: s1p-frontend-proxy
    ports:
      - "3000:80"
    volumes:
      - ./nginx/frontend.conf:/etc/nginx/conf.d/default.conf
    depends_on:
      - owner-frontend
      - company-frontend
    networks:
      - s1p-network

  # Owner panel frontend
  owner-frontend:
    build:
      context: ./frontend/owner
      dockerfile: Dockerfile
    container_name: s1p-owner-frontend
    environment:
      REACT_APP_API_URL: http://localhost:8000
      REACT_APP_APP_TYPE: owner
    volumes:
      - ./frontend/owner/src:/app/src
    networks:
      - s1p-network

  # Company panel frontend
  company-frontend:
    build:
      context: ./frontend/company
      dockerfile: Dockerfile
    container_name: s1p-company-frontend
    environment:
      REACT_APP_API_URL: http://localhost:8000
      REACT_APP_APP_TYPE: company
    volumes:
      - ./frontend/company/src:/app/src
    networks:
      - s1p-network

networks:
  s1p-network:
    external: true
    name: s1p_s1p-network
```

### Nginx Configuration

Create `nginx/frontend.conf`:

```nginx
# Owner panel: owners.localhost:3000
server {
    listen 80;
    server_name owners.localhost;

    location / {
        proxy_pass http://owner-frontend:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for HMR in development)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# Company panel: *.localhost:3000 (any subdomain except "owners")
server {
    listen 80;
    server_name ~^(?<subdomain>.+)\.localhost$;

    # Reject "owners" subdomain (handled above)
    if ($subdomain = "owners") {
        return 444;
    }

    location / {
        proxy_pass http://company-frontend:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for HMR in development)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Frontend Dockerfile (shared template)

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 3000
CMD ["npm", "start"]
```

### /etc/hosts Setup

Add to `/etc/hosts` on the development machine:

```
127.0.0.1 owners.localhost
127.0.0.1 mycompany.localhost
127.0.0.1 testcompany.localhost
```

### How It Works

1. User opens `http://owners.localhost:3000` → Nginx routes to **Owner Panel**
2. User opens `http://mycompany.localhost:3000` → Nginx routes to **Company Panel**
3. The **Company Panel** extracts the subdomain from `window.location.hostname` and sends it in the `Origin` header with every API request
4. The backend resolves the company from the `Origin` header

### API Client Configuration

```typescript
// Company frontend - api client
const subdomain = window.location.hostname.split('.')[0];

const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  headers: {
    'Origin': `http://${subdomain}.localhost:3000`,
  },
});

// Add JWT token to requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

---

## 3. Authentication & Authorization

### Company User Authentication Flow

```
┌─────────────────────────────────────────────────────────┐
│                    LOGIN FLOW                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  POST /api/v1/auth/login                                │
│  Headers: Origin: http://mycompany.localhost:3000       │
│  Body: { email, password }                             │
│                                                         │
│  ┌─── email_verified=true ──────────────────┐           │
│  │  Response: AuthorizedResponse            │           │
│  │  {                                       │           │
│  │    id, first_name, last_name, email,     │           │
│  │    is_active, must_change_password: false,│           │
│  │    credentials: {                        │           │
│  │      type: "Bearer",                     │           │
│  │      access: "<jwt>",                    │           │
│  │      refresh: "<jwt>"                    │           │
│  │    }                                     │           │
│  │  }                                       │           │
│  │  → Store tokens → Redirect to dashboard  │           │
│  └──────────────────────────────────────────┘           │
│                                                         │
│  ┌─── email_verified=false (first login) ───┐           │
│  │  Response: PasswordRequiredResponse      │           │
│  │  {                                       │           │
│  │    must_change_password: true,            │           │
│  │    temporary_token: "<jwt>"               │           │
│  │  }                                       │           │
│  │  → Redirect to Set Password page         │           │
│  └──────────────────────────────────────────┘           │
│                                                         │
│  SET PASSWORD (first login or forgot password):         │
│  POST /api/v1/auth/set-password                         │
│  Body: { token: "<temporary_token>",                    │
│          new_password: "NewPass1" }                     │
│  → Returns AuthorizedResponse with full tokens          │
│  → Store tokens → Redirect to dashboard                 │
│                                                         │
│  FORGOT PASSWORD:                                       │
│  POST /api/v1/auth/forgot-password                      │
│  Headers: Origin: http://mycompany.localhost:3000       │
│  Body: { email }                                       │
│  → Always returns 200 (prevents email enumeration)      │
│  → User receives email with reset link containing token │
│  → User clicks link → opens Set Password page           │
│  → POST /api/v1/auth/set-password with token            │
│                                                         │
│  CHANGE PASSWORD (authenticated user):                  │
│  POST /api/v1/auth/reset-password                       │
│  Headers: Authorization: Bearer <access_token>          │
│  Body: { old_password, new_password }                   │
│                                                         │
│  REFRESH TOKEN:                                         │
│  POST /api/v1/auth/refresh                              │
│  Body: { refresh_token: "<refresh_jwt>" }               │
│  → Returns { access: "<new_jwt>" }                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Owner Authentication Flow

Same pattern but at `/api/v1/owner/auth/*`:

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/owner/auth/login` | Owner login (no Origin needed) |
| `POST /api/v1/owner/auth/set-password` | Set password with token |
| `POST /api/v1/owner/auth/reset-password` | Change password (authenticated) |
| `POST /api/v1/owner/auth/forgot-password` | Request reset email |
| `GET /api/v1/owner/auth/me` | Get current owner profile |

### Token Management

| Token Type | Lifetime | Usage |
|------------|----------|-------|
| Access token | 15 days | `Authorization: Bearer <token>` header on all requests |
| Refresh token | 30 days | `POST /auth/refresh` to get new access token |
| Temporary token | 1 hour | Only for `set-password` endpoint |

### Password Requirements

```
- Minimum 8 characters
- At least one uppercase letter
- At least one digit
- Regex: ^(?=.*[A-Z])(?=.*\d).{8,}$
```

### Force Password Change

When a user is invited with a temporary password, `email_verified` is `false`. The system enforces password change:

1. Login returns `must_change_password: true` with a `temporary_token`
2. **All protected endpoints return 403** until password is changed
3. Only `set-password` works with the temporary token
4. After changing password, full tokens are returned

**Frontend must:**
- Check `must_change_password` in login response
- If `true`, redirect to a Set Password page
- Store the `temporary_token` and use it with `POST /auth/set-password`

---

## 4. API Endpoints — Company API

Full OpenAPI 3.1.0 specification for the Company API (`/api/v1/auth/*` + `/api/v1/company/*`):

<details>
<summary>Click to expand Company API OpenAPI JSON</summary>

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "S1P - Company API",
    "version": "0.1.0"
  },
  "paths": {
    "/api/v1/auth/login": {
      "post": {
        "tags": [
          "Auth"
        ],
        "summary": "Login",
        "description": "Login to a company.\n\nCompany is identified by the Origin header (subdomain).\nIf the user has a temporary password (email_verified=False),\nreturns a restricted token that only works with set-password.",
        "operationId": "login_api_v1_auth_login_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/LoginRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/auth/refresh": {
      "post": {
        "tags": [
          "Auth"
        ],
        "summary": "Refresh Token",
        "description": "Refresh access token using refresh token",
        "operationId": "refresh_token_api_v1_auth_refresh_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/RefreshTokenRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/auth/set-password": {
      "post": {
        "tags": [
          "Auth"
        ],
        "summary": "Set Password",
        "description": "Set new password using a temporary token.\n\nWorks for both flows:\n- First login: token from login response (purpose=set_password)\n- Forgot password: token from reset email (purpose=password_reset)\n\nReturns full access/refresh credentials on success.",
        "operationId": "set_password_api_v1_auth_set_password_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/SetPasswordRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/AuthorizedResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/auth/reset-password": {
      "post": {
        "tags": [
          "Auth"
        ],
        "summary": "Reset Password",
        "description": "Reset password (authenticated user who knows their current password).\n\nRequires old password for verification.",
        "operationId": "reset_password_api_v1_auth_reset_password_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ResetPasswordRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/auth/forgot-password": {
      "post": {
        "tags": [
          "Auth"
        ],
        "summary": "Forgot Password",
        "description": "Request a password reset email.\n\nCompany is identified by the Origin header (subdomain).\nAlways returns 200 to prevent email enumeration.",
        "operationId": "forgot_password_api_v1_auth_forgot_password_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ForgotPasswordRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/calls": {
      "post": {
        "tags": [
          "Company Operations",
          "Calls"
        ],
        "summary": "Make Call",
        "description": "Make a call (provider-agnostic)\n\nAutomatically routes to the correct provider (Sipuni or Binotel)\nbased on the company's configuration.\n\nFor Sipuni: `operator_id` is required and must be the internal SIP extension (e.g. '100001').\n`operator_id` can also be a user UUID, phone, or email — these are resolved to a user for CRM tracking.",
        "operationId": "make_call_api_v1_company_calls_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/CallRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CallResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "get": {
        "tags": [
          "Company Operations",
          "Calls"
        ],
        "summary": "List Calls",
        "description": "List all calls for the company",
        "operationId": "list_calls_api_v1_company_calls_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "skip",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "default": 0,
              "title": "Skip"
            }
          },
          {
            "name": "limit",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "default": 100,
              "title": "Limit"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "type": "array",
                  "items": {
                    "$ref": "#/components/schemas/CallEventResponse"
                  },
                  "title": "Response List Calls Api V1 Company Calls Get"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/calls/{call_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Calls"
        ],
        "summary": "Get Call",
        "description": "Get call details",
        "operationId": "get_call_api_v1_company_calls__call_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "call_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Call Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CallEventResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/calls/{call_id}/recording": {
      "get": {
        "tags": [
          "Company Operations",
          "Calls"
        ],
        "summary": "Get Call Recording",
        "description": "Get proxied call recording URL\n\nReturns a secure, time-limited URL to access the call recording.\nThe URL is signed and expires after the configured time period.",
        "operationId": "get_call_recording_api_v1_company_calls__call_id__recording_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "call_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Call Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CallRecordingURL"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/calls/{call_id}/outcome": {
      "put": {
        "tags": [
          "Company Operations",
          "Calls - Enhanced"
        ],
        "summary": "Set Call Outcome",
        "description": "Set call outcome/disposition\n\nOperators can set outcomes for calls to track results.",
        "operationId": "set_call_outcome_api_v1_company_calls__call_id__outcome_put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "call_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Call Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/CallOutcomeUpdate"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/calls/{call_id}/link": {
      "post": {
        "tags": [
          "Company Operations",
          "Calls - Enhanced"
        ],
        "summary": "Link Call To Crm",
        "description": "Link call to CRM entities (contact, lead, deal)\n\nAssociates a call with CRM records for tracking and reporting.",
        "operationId": "link_call_to_crm_api_v1_company_calls__call_id__link_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "call_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Call Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/CallLinkRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/calls/history": {
      "get": {
        "tags": [
          "Company Operations",
          "Calls - Enhanced"
        ],
        "summary": "Get Call History",
        "description": "Enhanced call history with comprehensive filters\n\nSupports filtering by direction, outcome, operator, CRM entities, and date range.",
        "operationId": "get_call_history_api_v1_company_calls_history_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "minimum": 1,
              "default": 1,
              "title": "Page"
            }
          },
          {
            "name": "page_size",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "maximum": 100,
              "minimum": 1,
              "default": 20,
              "title": "Page Size"
            }
          },
          {
            "name": "search",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Search"
            }
          },
          {
            "name": "direction",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Direction"
            }
          },
          {
            "name": "outcome",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Outcome"
            }
          },
          {
            "name": "operator_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Operator Id"
            }
          },
          {
            "name": "contact_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Contact Id"
            }
          },
          {
            "name": "lead_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Lead Id"
            }
          },
          {
            "name": "deal_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Deal Id"
            }
          },
          {
            "name": "date_from",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date From"
            }
          },
          {
            "name": "date_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date To"
            }
          },
          {
            "name": "my_calls",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "description": "Show only my calls",
              "default": false,
              "title": "My Calls"
            },
            "description": "Show only my calls"
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PaginatedResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/calls/outcomes/summary": {
      "get": {
        "tags": [
          "Company Operations",
          "Calls - Enhanced"
        ],
        "summary": "Get Call Outcomes Summary",
        "description": "Get call outcomes summary statistics\n\nReturns counts and percentages for each outcome type.",
        "operationId": "get_call_outcomes_summary_api_v1_company_calls_outcomes_summary_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "date_from",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date From"
            }
          },
          {
            "name": "date_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date To"
            }
          },
          {
            "name": "operator_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Operator Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/calls/auto-link-suggestions/{phone_number}": {
      "get": {
        "tags": [
          "Company Operations",
          "Calls - Enhanced"
        ],
        "summary": "Get Auto Link Suggestions",
        "description": "Get suggestions for linking a call to CRM entities\n\nSearches for contacts, leads, and deals that match the phone number.",
        "operationId": "get_auto_link_suggestions_api_v1_company_calls_auto_link_suggestions__phone_number__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "phone_number",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Phone Number"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/webhooks/{token}": {
      "post": {
        "tags": [
          "Company Operations",
          "Webhooks"
        ],
        "summary": "Handle Webhook",
        "description": "Unified webhook endpoint for all telephony providers\n\nRoutes webhook to the correct provider handler based on company configuration.\nProviders normalize their webhook data into a unified format.\n\nSecurity:\n- Validates webhook token\n- Validates source IP against provider whitelist\n- Validates provider-specific authentication",
        "operationId": "handle_webhook_api_v1_company_webhooks__token__post",
        "parameters": [
          {
            "name": "token",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Token"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/recordings/proxy/{token}": {
      "get": {
        "tags": [
          "Company Operations",
          "Recordings"
        ],
        "summary": "Proxy Recording",
        "description": "Proxy endpoint for call recordings\n\nValidates the signed token and redirects to the actual recording URL.\nThis provides secure, time-limited access to call recordings without\nexposing provider URLs directly.",
        "operationId": "proxy_recording_api_v1_company_recordings_proxy__token__get",
        "parameters": [
          {
            "name": "token",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Token"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/recordings/stream/{token}": {
      "get": {
        "tags": [
          "Company Operations",
          "Recordings"
        ],
        "summary": "Stream Recording",
        "description": "Stream call recording directly (more secure than redirect)\n\nValidates the token and streams the recording file directly\nwithout exposing the provider URL.",
        "operationId": "stream_recording_api_v1_company_recordings_stream__token__get",
        "parameters": [
          {
            "name": "token",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Token"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/users/invite": {
      "post": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "Invite Operator",
        "description": "Invite a new operator (Company Admin only)\n\nSends email invitation with temporary password.\nOperator must change password on first login.",
        "operationId": "invite_operator_api_v1_company_users_invite_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/UserInviteRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/users/me": {
      "get": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "Get My Profile",
        "description": "Get current user's own profile",
        "operationId": "get_my_profile_api_v1_company_users_me_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserResponse"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      },
      "put": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "Update My Profile",
        "description": "Update current user's own profile\n\nOnly personal fields can be updated (name, phone, language).",
        "operationId": "update_my_profile_api_v1_company_users_me_put",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ProfileUpdateRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/users": {
      "get": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "List Users",
        "description": "List all users in the company (Company Admin only)\n\nSupports pagination, filtering by role/status, and search.",
        "operationId": "list_users_api_v1_company_users_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "minimum": 1,
              "default": 1,
              "title": "Page"
            }
          },
          {
            "name": "page_size",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "maximum": 100,
              "minimum": 1,
              "default": 20,
              "title": "Page Size"
            }
          },
          {
            "name": "role",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Role"
            }
          },
          {
            "name": "is_active",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "boolean"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Is Active"
            }
          },
          {
            "name": "search",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Search"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserListResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/users/{user_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "Get User",
        "description": "Get user details with statistics\n\nIncludes total calls, leads, deals, and tasks.",
        "operationId": "get_user_api_v1_company_users__user_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "user_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "User Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserDetailResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "Update User",
        "description": "Update user information (Company Admin only)\n\nCan update name, phone, role, permissions, and status.",
        "operationId": "update_user_api_v1_company_users__user_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "user_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "User Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/UserUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "delete": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "Delete User",
        "description": "Delete user (Company Admin only)\n\nBy default performs soft delete (can be restored).\nUse hard=true for permanent deletion.",
        "operationId": "delete_user_api_v1_company_users__user_id__delete",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "user_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "User Id"
            }
          },
          {
            "name": "hard",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "default": false,
              "title": "Hard"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/users/{user_id}/activate": {
      "post": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "Activate User",
        "description": "Activate a suspended user",
        "operationId": "activate_user_api_v1_company_users__user_id__activate_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "user_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "User Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/users/{user_id}/deactivate": {
      "post": {
        "tags": [
          "Company Operations",
          "User Management"
        ],
        "summary": "Deactivate User",
        "description": "Deactivate a user (suspend access)",
        "operationId": "deactivate_user_api_v1_company_users__user_id__deactivate_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "user_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "User Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/analytics/me": {
      "get": {
        "tags": [
          "Company Operations",
          "Analytics"
        ],
        "summary": "Get My Analytics",
        "description": "Get my personal analytics (Operator/Anyone)\n\nReturns performance metrics for the current user.\nUses SQL aggregations for optimal performance.",
        "operationId": "get_my_analytics_api_v1_company_analytics_me_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "period",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "description": "today, week, month, year",
              "default": "month",
              "title": "Period"
            },
            "description": "today, week, month, year"
          },
          {
            "name": "date_from",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date From"
            }
          },
          {
            "name": "date_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date To"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OperatorAnalytics"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/analytics/me/dashboard": {
      "get": {
        "tags": [
          "Company Operations",
          "Analytics"
        ],
        "summary": "Get My Dashboard",
        "description": "Get my dashboard data (Operator/Anyone)\n\nOPTIMIZED: Uses caching and SQL aggregations.\nReturns dashboard with today, week, and month analytics plus quick stats.",
        "operationId": "get_my_dashboard_api_v1_company_analytics_me_dashboard_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OperatorDashboard"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/analytics/team": {
      "get": {
        "tags": [
          "Company Operations",
          "Analytics"
        ],
        "summary": "Get Team Analytics",
        "description": "Get team analytics (Admin only)\n\nOPTIMIZED: Uses SQL aggregations and single query for operator stats.\nReturns aggregated performance metrics for all operators.",
        "operationId": "get_team_analytics_api_v1_company_analytics_team_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "period",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "description": "today, week, month, year",
              "default": "month",
              "title": "Period"
            },
            "description": "today, week, month, year"
          },
          {
            "name": "date_from",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date From"
            }
          },
          {
            "name": "date_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date To"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/TeamAnalytics"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/analytics/team/dashboard": {
      "get": {
        "tags": [
          "Company Operations",
          "Analytics"
        ],
        "summary": "Get Admin Dashboard",
        "description": "Get admin dashboard (Admin only)\n\nOPTIMIZED:\n- Uses caching (5 minute TTL)\n- Single query for trends instead of N queries\n- SQL aggregations for all stats",
        "operationId": "get_admin_dashboard_api_v1_company_analytics_team_dashboard_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/AdminDashboard"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/analytics/operator/{user_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Analytics"
        ],
        "summary": "Get Operator Analytics",
        "description": "Get specific operator analytics (Admin only)\n\nReturns performance metrics for a specific operator.\nUses SQL aggregations for optimal performance.",
        "operationId": "get_operator_analytics_api_v1_company_analytics_operator__user_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "user_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "User Id"
            }
          },
          {
            "name": "period",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "description": "today, week, month, year",
              "default": "month",
              "title": "Period"
            },
            "description": "today, week, month, year"
          },
          {
            "name": "date_from",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date From"
            }
          },
          {
            "name": "date_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date To"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OperatorAnalytics"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/analytics/cache": {
      "delete": {
        "tags": [
          "Company Operations",
          "Analytics"
        ],
        "summary": "Clear Analytics Cache",
        "description": "Clear analytics cache for this company\n\nUse this after bulk data imports or when you need fresh data.",
        "operationId": "clear_analytics_cache_api_v1_company_analytics_cache_delete",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/contract": {
      "get": {
        "tags": [
          "Company Operations",
          "Company Contract"
        ],
        "summary": "Get Contract Status",
        "description": "View own company's contract status with limits, usage, and warnings.",
        "operationId": "get_contract_status_api_v1_company_contract_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContractStatusResponse"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/permission-groups/permissions": {
      "get": {
        "tags": [
          "Company Operations",
          "Permission Groups",
          "Permission Groups"
        ],
        "summary": "List Available Permissions",
        "description": "List all available permission strings\n\nReturns permissions grouped by resource.",
        "operationId": "list_available_permissions_api_v1_company_permission_groups_permissions_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/permission-groups": {
      "get": {
        "tags": [
          "Company Operations",
          "Permission Groups"
        ],
        "summary": "List Permission Groups",
        "description": "List all permission groups available to the company\n\nReturns system groups (shared) + company-specific custom groups.",
        "operationId": "list_permission_groups_api_v1_company_permission_groups_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PermissionGroupListResponse"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      },
      "post": {
        "tags": [
          "Company Operations",
          "Permission Groups"
        ],
        "summary": "Create Permission Group",
        "description": "Create a custom permission group for the company",
        "operationId": "create_permission_group_api_v1_company_permission_groups_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/PermissionGroupCreateRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PermissionGroupResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/permission-groups/{group_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Permission Groups"
        ],
        "summary": "Get Permission Group",
        "description": "Get a single permission group",
        "operationId": "get_permission_group_api_v1_company_permission_groups__group_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "group_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Group Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PermissionGroupResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Company Operations",
          "Permission Groups"
        ],
        "summary": "Update Permission Group",
        "description": "Update a custom permission group\n\nSystem groups cannot be modified.",
        "operationId": "update_permission_group_api_v1_company_permission_groups__group_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "group_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Group Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/PermissionGroupUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PermissionGroupResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "delete": {
        "tags": [
          "Company Operations",
          "Permission Groups"
        ],
        "summary": "Delete Permission Group",
        "description": "Soft-delete a custom permission group\n\nSystem groups cannot be deleted.\nNullifies permission_group_id on affected users before deleting.",
        "operationId": "delete_permission_group_api_v1_company_permission_groups__group_id__delete",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "group_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Group Id"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/contacts": {
      "post": {
        "tags": [
          "Company Operations",
          "Contacts"
        ],
        "summary": "Create Contact",
        "description": "Create a new contact\n\nContacts are the foundation of the CRM. They can be linked to leads, deals, and calls.",
        "operationId": "create_contact_api_v1_company_contacts_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ContactCreateRequest"
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContactResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "get": {
        "tags": [
          "Company Operations",
          "Contacts"
        ],
        "summary": "List Contacts",
        "description": "List all contacts with filters and search\n\nOPTIMIZED: Uses subqueries for related counts instead of N+1 queries.\nSingle query returns contacts with all counts.",
        "operationId": "list_contacts_api_v1_company_contacts_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "minimum": 1,
              "default": 1,
              "title": "Page"
            }
          },
          {
            "name": "page_size",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "maximum": 100,
              "minimum": 1,
              "default": 20,
              "title": "Page Size"
            }
          },
          {
            "name": "search",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Search"
            }
          },
          {
            "name": "assigned_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Assigned To"
            }
          },
          {
            "name": "has_email",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "boolean"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Has Email"
            }
          },
          {
            "name": "has_phone",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "boolean"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Has Phone"
            }
          },
          {
            "name": "created_by",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Created By"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PaginatedResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/contacts/{contact_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Contacts"
        ],
        "summary": "Get Contact",
        "description": "Get contact details\n\nReturns full contact information with related counts (single query).",
        "operationId": "get_contact_api_v1_company_contacts__contact_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "contact_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Contact Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContactResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Company Operations",
          "Contacts"
        ],
        "summary": "Update Contact",
        "description": "Update contact information\n\nSupports partial updates (only provided fields are updated).",
        "operationId": "update_contact_api_v1_company_contacts__contact_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "contact_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Contact Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ContactUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContactResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "delete": {
        "tags": [
          "Company Operations",
          "Contacts"
        ],
        "summary": "Delete Contact",
        "description": "Delete a contact\n\nBy default performs soft delete. Use hard=true for permanent deletion.",
        "operationId": "delete_contact_api_v1_company_contacts__contact_id__delete",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "contact_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Contact Id"
            }
          },
          {
            "name": "hard",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "description": "Permanent deletion",
              "default": false,
              "title": "Hard"
            },
            "description": "Permanent deletion"
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/contacts/{contact_id}/activity": {
      "get": {
        "tags": [
          "Company Operations",
          "Contacts"
        ],
        "summary": "Get Contact Activity",
        "description": "Get contact activity timeline\n\nReturns leads, deals, calls related to this contact.\nUses optimized queries with limits.",
        "operationId": "get_contact_activity_api_v1_company_contacts__contact_id__activity_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "contact_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Contact Id"
            }
          },
          {
            "name": "limit",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "maximum": 100,
              "minimum": 1,
              "default": 20,
              "title": "Limit"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/contacts/bulk": {
      "post": {
        "tags": [
          "Company Operations",
          "Contacts"
        ],
        "summary": "Bulk Create Contacts",
        "description": "Bulk create contacts\n\nEfficiently creates multiple contacts in a single transaction.\nMaximum 100 contacts per request.",
        "operationId": "bulk_create_contacts_api_v1_company_contacts_bulk_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "items": {
                  "$ref": "#/components/schemas/ContactCreateRequest"
                },
                "type": "array",
                "title": "Contacts"
              }
            }
          },
          "required": true
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "items": {
                    "$ref": "#/components/schemas/ContactResponse"
                  },
                  "type": "array",
                  "title": "Response Bulk Create Contacts Api V1 Company Contacts Bulk Post"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/leads": {
      "post": {
        "tags": [
          "Company Operations",
          "Leads"
        ],
        "summary": "Create Lead",
        "description": "Create a new lead\n\nLeads represent potential sales opportunities. They can be linked to contacts.",
        "operationId": "create_lead_api_v1_company_leads_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/LeadCreateRequest"
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/LeadResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "get": {
        "tags": [
          "Company Operations",
          "Leads"
        ],
        "summary": "List Leads",
        "description": "List all leads with filters\n\nOperators see all leads by default, but can filter to show only their assigned leads.",
        "operationId": "list_leads_api_v1_company_leads_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "minimum": 1,
              "default": 1,
              "title": "Page"
            }
          },
          {
            "name": "page_size",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "maximum": 100,
              "minimum": 1,
              "default": 20,
              "title": "Page Size"
            }
          },
          {
            "name": "search",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Search"
            }
          },
          {
            "name": "status_filter",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Status Filter"
            }
          },
          {
            "name": "assigned_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Assigned To"
            }
          },
          {
            "name": "source",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Source"
            }
          },
          {
            "name": "min_value",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "number"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Min Value"
            }
          },
          {
            "name": "max_value",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "number"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Max Value"
            }
          },
          {
            "name": "my_leads",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "description": "Show only my assigned leads",
              "default": false,
              "title": "My Leads"
            },
            "description": "Show only my assigned leads"
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PaginatedResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/leads/{lead_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Leads"
        ],
        "summary": "Get Lead",
        "description": "Get lead details",
        "operationId": "get_lead_api_v1_company_leads__lead_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "lead_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Lead Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/LeadResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Company Operations",
          "Leads"
        ],
        "summary": "Update Lead",
        "description": "Update lead information\n\nSupports status changes through the lead lifecycle.",
        "operationId": "update_lead_api_v1_company_leads__lead_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "lead_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Lead Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/LeadUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/LeadResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "delete": {
        "tags": [
          "Company Operations",
          "Leads"
        ],
        "summary": "Delete Lead",
        "description": "Delete a lead",
        "operationId": "delete_lead_api_v1_company_leads__lead_id__delete",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "lead_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Lead Id"
            }
          },
          {
            "name": "hard",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "default": false,
              "title": "Hard"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/leads/{lead_id}/convert": {
      "post": {
        "tags": [
          "Company Operations",
          "Leads"
        ],
        "summary": "Convert Lead",
        "description": "Convert lead to customer\n\nOptionally creates a deal from the lead and marks the lead as converted.",
        "operationId": "convert_lead_api_v1_company_leads__lead_id__convert_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "lead_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Lead Id"
            }
          },
          {
            "name": "create_deal",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "description": "Create deal from lead",
              "default": true,
              "title": "Create Deal"
            },
            "description": "Create deal from lead"
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "additionalProperties": true,
                  "title": "Response Convert Lead Api V1 Company Leads  Lead Id  Convert Post"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/leads/{lead_id}/assign": {
      "post": {
        "tags": [
          "Company Operations",
          "Leads"
        ],
        "summary": "Assign Lead",
        "description": "Assign lead to an operator\n\nOnly admins can assign leads.",
        "operationId": "assign_lead_api_v1_company_leads__lead_id__assign_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "lead_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Lead Id"
            }
          },
          {
            "name": "assigned_to",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Assigned To"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/LeadResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/deals": {
      "post": {
        "tags": [
          "Company Operations",
          "Deals"
        ],
        "summary": "Create Deal",
        "description": "Create a new deal\n\nDeals represent active sales opportunities with monetary value.",
        "operationId": "create_deal_api_v1_company_deals_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/DealCreateRequest"
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/DealResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "get": {
        "tags": [
          "Company Operations",
          "Deals"
        ],
        "summary": "List Deals",
        "description": "List all deals with filters\n\nPipeline view: filter by stage to see deals in different stages.",
        "operationId": "list_deals_api_v1_company_deals_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "minimum": 1,
              "default": 1,
              "title": "Page"
            }
          },
          {
            "name": "page_size",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "maximum": 100,
              "minimum": 1,
              "default": 20,
              "title": "Page Size"
            }
          },
          {
            "name": "search",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Search"
            }
          },
          {
            "name": "stage",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Stage"
            }
          },
          {
            "name": "assigned_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Assigned To"
            }
          },
          {
            "name": "min_value",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "number"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Min Value"
            }
          },
          {
            "name": "max_value",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "number"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Max Value"
            }
          },
          {
            "name": "my_deals",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "description": "Show only my assigned deals",
              "default": false,
              "title": "My Deals"
            },
            "description": "Show only my assigned deals"
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PaginatedResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/deals/{deal_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Deals"
        ],
        "summary": "Get Deal",
        "description": "Get deal details",
        "operationId": "get_deal_api_v1_company_deals__deal_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "deal_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Deal Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/DealResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Company Operations",
          "Deals"
        ],
        "summary": "Update Deal",
        "description": "Update deal information\n\nSupports moving deals through pipeline stages.",
        "operationId": "update_deal_api_v1_company_deals__deal_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "deal_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Deal Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/DealUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/DealResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "delete": {
        "tags": [
          "Company Operations",
          "Deals"
        ],
        "summary": "Delete Deal",
        "description": "Delete a deal",
        "operationId": "delete_deal_api_v1_company_deals__deal_id__delete",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "deal_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Deal Id"
            }
          },
          {
            "name": "hard",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "default": false,
              "title": "Hard"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/deals/{deal_id}/win": {
      "post": {
        "tags": [
          "Company Operations",
          "Deals"
        ],
        "summary": "Mark Deal Won",
        "description": "Mark deal as won\n\nRecords win reason and closes the deal.",
        "operationId": "mark_deal_won_api_v1_company_deals__deal_id__win_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "deal_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Deal Id"
            }
          },
          {
            "name": "win_reason",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Win Reason"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/DealResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/deals/{deal_id}/lose": {
      "post": {
        "tags": [
          "Company Operations",
          "Deals"
        ],
        "summary": "Mark Deal Lost",
        "description": "Mark deal as lost\n\nRecords loss reason and closes the deal.",
        "operationId": "mark_deal_lost_api_v1_company_deals__deal_id__lose_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "deal_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Deal Id"
            }
          },
          {
            "name": "loss_reason",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Loss Reason"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/DealResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/deals/pipeline/summary": {
      "get": {
        "tags": [
          "Company Operations",
          "Deals"
        ],
        "summary": "Get Pipeline Summary",
        "description": "Get pipeline summary\n\nReturns deal counts and values by stage.",
        "operationId": "get_pipeline_summary_api_v1_company_deals_pipeline_summary_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/tasks": {
      "post": {
        "tags": [
          "Company Operations",
          "Tasks"
        ],
        "summary": "Create Task",
        "description": "Create a new task\n\nTasks can be linked to contacts, leads, or deals for context.",
        "operationId": "create_task_api_v1_company_tasks_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/TaskCreateRequest"
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/TaskResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "get": {
        "tags": [
          "Company Operations",
          "Tasks"
        ],
        "summary": "List Tasks",
        "description": "List all tasks with filters\n\nOperators see all tasks by default, but typically filter to show only their tasks.",
        "operationId": "list_tasks_api_v1_company_tasks_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "minimum": 1,
              "default": 1,
              "title": "Page"
            }
          },
          {
            "name": "page_size",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "maximum": 100,
              "minimum": 1,
              "default": 20,
              "title": "Page Size"
            }
          },
          {
            "name": "search",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Search"
            }
          },
          {
            "name": "status_filter",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Status Filter"
            }
          },
          {
            "name": "priority",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Priority"
            }
          },
          {
            "name": "assigned_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Assigned To"
            }
          },
          {
            "name": "overdue",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "description": "Show only overdue tasks",
              "default": false,
              "title": "Overdue"
            },
            "description": "Show only overdue tasks"
          },
          {
            "name": "my_tasks",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "description": "Show only my assigned tasks",
              "default": false,
              "title": "My Tasks"
            },
            "description": "Show only my assigned tasks"
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PaginatedResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/tasks/my-today": {
      "get": {
        "tags": [
          "Company Operations",
          "Tasks"
        ],
        "summary": "Get My Tasks Today",
        "description": "Get my tasks for today\n\nReturns pending tasks due today or overdue.",
        "operationId": "get_my_tasks_today_api_v1_company_tasks_my_today_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "items": {},
                  "type": "array",
                  "title": "Response Get My Tasks Today Api V1 Company Tasks My Today Get"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/company/tasks/{task_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Tasks"
        ],
        "summary": "Get Task",
        "description": "Get task details",
        "operationId": "get_task_api_v1_company_tasks__task_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "task_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Task Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/TaskResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Company Operations",
          "Tasks"
        ],
        "summary": "Update Task",
        "description": "Update task information\n\nOperators can update their own tasks. Admins can update all tasks.",
        "operationId": "update_task_api_v1_company_tasks__task_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "task_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Task Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/TaskUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/TaskResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "delete": {
        "tags": [
          "Company Operations",
          "Tasks"
        ],
        "summary": "Delete Task",
        "description": "Delete a task (Admins only)",
        "operationId": "delete_task_api_v1_company_tasks__task_id__delete",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "task_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Task Id"
            }
          },
          {
            "name": "hard",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "default": false,
              "title": "Hard"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/tasks/{task_id}/complete": {
      "post": {
        "tags": [
          "Company Operations",
          "Tasks"
        ],
        "summary": "Complete Task",
        "description": "Mark task as completed\n\nAny assigned user can complete their task.",
        "operationId": "complete_task_api_v1_company_tasks__task_id__complete_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "task_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Task Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/TaskResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/notes": {
      "post": {
        "tags": [
          "Company Operations",
          "Notes"
        ],
        "summary": "Create Note",
        "description": "Create a new note\n\nNotes can be attached to contacts, leads, deals, tasks, or calls.",
        "operationId": "create_note_api_v1_company_notes_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/NoteCreateRequest"
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/NoteResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "get": {
        "tags": [
          "Company Operations",
          "Notes"
        ],
        "summary": "List Notes",
        "description": "List all notes with filters\n\nCan filter by entity (contact, lead, deal, task, call) or creator.",
        "operationId": "list_notes_api_v1_company_notes_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "page",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "minimum": 1,
              "default": 1,
              "title": "Page"
            }
          },
          {
            "name": "page_size",
            "in": "query",
            "required": false,
            "schema": {
              "type": "integer",
              "maximum": 100,
              "minimum": 1,
              "default": 20,
              "title": "Page Size"
            }
          },
          {
            "name": "search",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Search"
            }
          },
          {
            "name": "contact_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Contact Id"
            }
          },
          {
            "name": "lead_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Lead Id"
            }
          },
          {
            "name": "deal_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Deal Id"
            }
          },
          {
            "name": "task_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Task Id"
            }
          },
          {
            "name": "call_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Call Id"
            }
          },
          {
            "name": "created_by",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Created By"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PaginatedResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/notes/{note_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Notes"
        ],
        "summary": "Get Note",
        "description": "Get note details",
        "operationId": "get_note_api_v1_company_notes__note_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "note_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Note Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/NoteResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Company Operations",
          "Notes"
        ],
        "summary": "Update Note",
        "description": "Update note content\n\nUsers can only update their own notes (unless admin).",
        "operationId": "update_note_api_v1_company_notes__note_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "note_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Note Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/NoteUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/NoteResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "delete": {
        "tags": [
          "Company Operations",
          "Notes"
        ],
        "summary": "Delete Note",
        "description": "Delete a note\n\nUsers can only delete their own notes (unless admin).",
        "operationId": "delete_note_api_v1_company_notes__note_id__delete",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "note_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Note Id"
            }
          },
          {
            "name": "hard",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "default": false,
              "title": "Hard"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/company/notes/timeline/{entity_type}/{entity_id}": {
      "get": {
        "tags": [
          "Company Operations",
          "Notes"
        ],
        "summary": "Get Entity Notes",
        "description": "Get all notes for an entity\n\nentity_type: contact, lead, deal, task, call\nReturns notes in chronological order.",
        "operationId": "get_entity_notes_api_v1_company_notes_timeline__entity_type___entity_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "entity_type",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Entity Type"
            }
          },
          {
            "name": "entity_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Entity Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "AdminDashboard": {
        "properties": {
          "today": {
            "$ref": "#/components/schemas/TeamAnalytics"
          },
          "this_week": {
            "$ref": "#/components/schemas/TeamAnalytics"
          },
          "this_month": {
            "$ref": "#/components/schemas/TeamAnalytics"
          },
          "this_year": {
            "$ref": "#/components/schemas/TeamAnalytics"
          },
          "conversion_funnel": {
            "$ref": "#/components/schemas/ConversionFunnel"
          },
          "pipeline_health": {
            "$ref": "#/components/schemas/PipelineHealth"
          },
          "peak_call_hours": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Peak Call Hours",
            "default": []
          },
          "calls_trend": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Calls Trend",
            "default": []
          },
          "revenue_trend": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Revenue Trend",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "today",
          "this_week",
          "this_month",
          "this_year",
          "conversion_funnel",
          "pipeline_health"
        ],
        "title": "AdminDashboard",
        "description": "Admin dashboard data"
      },
      "AuthorizedResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "first_name": {
            "type": "string",
            "maxLength": 255,
            "title": "First Name"
          },
          "last_name": {
            "type": "string",
            "maxLength": 255,
            "title": "Last Name"
          },
          "email": {
            "type": "string",
            "maxLength": 2048,
            "title": "Email"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "must_change_password": {
            "type": "boolean",
            "title": "Must Change Password",
            "default": false
          },
          "credentials": {
            "$ref": "#/components/schemas/BearerToken"
          }
        },
        "type": "object",
        "required": [
          "id",
          "first_name",
          "last_name",
          "email",
          "is_active",
          "credentials"
        ],
        "title": "AuthorizedResponse"
      },
      "BearerToken": {
        "properties": {
          "type": {
            "type": "string",
            "title": "Type",
            "default": "Bearer"
          },
          "access": {
            "type": "string",
            "title": "Access"
          },
          "refresh": {
            "type": "string",
            "title": "Refresh"
          }
        },
        "type": "object",
        "required": [
          "access",
          "refresh"
        ],
        "title": "BearerToken"
      },
      "BillingPeriodEnum": {
        "type": "string",
        "enum": [
          "monthly",
          "yearly"
        ],
        "title": "BillingPeriodEnum",
        "description": "Billing period enumeration"
      },
      "CallDirectionEnum": {
        "type": "string",
        "enum": [
          "inbound",
          "outbound",
          "internal"
        ],
        "title": "CallDirectionEnum",
        "description": "Call direction enumeration"
      },
      "CallEventResponse": {
        "properties": {
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "provider_type": {
            "$ref": "#/components/schemas/ProviderEnum"
          },
          "provider_call_id": {
            "type": "string",
            "title": "Provider Call Id"
          },
          "phone_1": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone 1"
          },
          "phone_2": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone 2"
          },
          "operator_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Operator Id"
          },
          "direction": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/CallDirectionEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "state": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/CallStatusEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "attempts": {
            "type": "integer",
            "title": "Attempts"
          },
          "waiting_sec": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Waiting Sec"
          },
          "billing_sec": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Billing Sec"
          },
          "record_url": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Record Url"
          },
          "call_start_timestamp": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Call Start Timestamp"
          },
          "call_end_timestamp": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Call End Timestamp"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          }
        },
        "type": "object",
        "required": [
          "created_at",
          "updated_at",
          "id",
          "company_id",
          "provider_type",
          "provider_call_id",
          "attempts"
        ],
        "title": "CallEventResponse",
        "description": "Call event response"
      },
      "CallLinkRequest": {
        "properties": {
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          },
          "deal_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Deal Id"
          }
        },
        "type": "object",
        "title": "CallLinkRequest",
        "description": "Link call to CRM entities"
      },
      "CallOutcomeUpdate": {
        "properties": {
          "outcome": {
            "type": "string",
            "title": "Outcome",
            "description": "Call outcome"
          },
          "disposition_notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Disposition Notes",
            "description": "Notes about the call"
          }
        },
        "type": "object",
        "required": [
          "outcome"
        ],
        "title": "CallOutcomeUpdate",
        "description": "Update call outcome"
      },
      "CallRecordingURL": {
        "properties": {
          "url": {
            "type": "string",
            "title": "Url"
          },
          "expires_in": {
            "type": "integer",
            "title": "Expires In"
          }
        },
        "type": "object",
        "required": [
          "url",
          "expires_in"
        ],
        "title": "CallRecordingURL",
        "description": "Call recording URL response"
      },
      "CallRequest": {
        "properties": {
          "phone_1": {
            "type": "string",
            "title": "Phone 1",
            "description": "First phone number (caller or external)"
          },
          "phone_2": {
            "type": "string",
            "title": "Phone 2",
            "description": "Second phone number (receiver or internal)"
          },
          "operator_id": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Operator Id",
            "description": "Operator identifier: UUID, phone, email, or SIP extension (e.g. '100001'). For Sipuni, this is the internal SIP number and is required."
          },
          "order_id": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Order Id",
            "description": "External order/ticket ID"
          },
          "utm_source": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Utm Source"
          },
          "utm_medium": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Utm Medium"
          },
          "utm_campaign": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Utm Campaign"
          }
        },
        "type": "object",
        "required": [
          "phone_1",
          "phone_2"
        ],
        "title": "CallRequest",
        "description": "Request to initiate a call"
      },
      "CallResponse": {
        "properties": {
          "success": {
            "type": "boolean",
            "title": "Success"
          },
          "call_id": {
            "type": "string",
            "title": "Call Id",
            "description": "Provider's call ID"
          },
          "message": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Message"
          },
          "error": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Error"
          }
        },
        "type": "object",
        "required": [
          "success",
          "call_id"
        ],
        "title": "CallResponse",
        "description": "Response from call initiation"
      },
      "CallStats": {
        "properties": {
          "total_calls": {
            "type": "integer",
            "title": "Total Calls",
            "default": 0
          },
          "answered_calls": {
            "type": "integer",
            "title": "Answered Calls",
            "default": 0
          },
          "missed_calls": {
            "type": "integer",
            "title": "Missed Calls",
            "default": 0
          },
          "outbound_calls": {
            "type": "integer",
            "title": "Outbound Calls",
            "default": 0
          },
          "inbound_calls": {
            "type": "integer",
            "title": "Inbound Calls",
            "default": 0
          },
          "total_duration": {
            "type": "integer",
            "title": "Total Duration",
            "default": 0
          },
          "average_duration": {
            "type": "number",
            "title": "Average Duration",
            "default": 0.0
          },
          "success_rate": {
            "type": "number",
            "title": "Success Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "CallStats",
        "description": "Call statistics"
      },
      "CallStatusEnum": {
        "type": "string",
        "enum": [
          "ANSWER",
          "BUSY",
          "NOANSWER",
          "CANCEL",
          "CONGESTION",
          "CHANUNAVAIL"
        ],
        "title": "CallStatusEnum",
        "description": "Call status enumeration"
      },
      "CompanyCreateRequest": {
        "properties": {
          "name": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Name"
          },
          "subdomain": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Subdomain",
            "description": "Company subdomain (auto-generated if not provided)"
          },
          "provider_type": {
            "type": "string",
            "title": "Provider Type",
            "description": "Provider: sipuni or binotel"
          },
          "provider_config": {
            "additionalProperties": true,
            "type": "object",
            "title": "Provider Config",
            "description": "Provider-specific configuration (requires cabinet_id and security_key)"
          },
          "settings": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Settings"
          }
        },
        "type": "object",
        "required": [
          "name",
          "provider_type",
          "provider_config"
        ],
        "title": "CompanyCreateRequest",
        "description": "Create company request",
        "example": {
          "name": "My Company LLC",
          "provider_config": {
            "cabinet_id": "12345",
            "security_key": "your-secret-key"
          },
          "provider_type": "sipuni",
          "settings": {
            "language": "ru",
            "timezone": "Asia/Tashkent"
          },
          "subdomain": "mycompany"
        }
      },
      "CompanyDetailResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "subdomain": {
            "type": "string",
            "title": "Subdomain"
          },
          "provider_type": {
            "type": "string",
            "title": "Provider Type"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "webhook_url": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Webhook Url"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "provider_config": {
            "additionalProperties": true,
            "type": "object",
            "title": "Provider Config"
          },
          "settings": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Settings"
          },
          "webhook_token": {
            "type": "string",
            "title": "Webhook Token"
          }
        },
        "type": "object",
        "required": [
          "id",
          "name",
          "subdomain",
          "provider_type",
          "is_active",
          "created_at",
          "updated_at",
          "provider_config",
          "webhook_token"
        ],
        "title": "CompanyDetailResponse",
        "description": "Detailed company response with config"
      },
      "CompanyPerformance": {
        "properties": {
          "company_id": {
            "type": "string",
            "title": "Company Id"
          },
          "company_name": {
            "type": "string",
            "title": "Company Name"
          },
          "total_users": {
            "type": "integer",
            "title": "Total Users",
            "default": 0
          },
          "active_users": {
            "type": "integer",
            "title": "Active Users",
            "default": 0
          },
          "total_calls": {
            "type": "integer",
            "title": "Total Calls",
            "default": 0
          },
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "total_deals": {
            "type": "integer",
            "title": "Total Deals",
            "default": 0
          },
          "total_revenue": {
            "type": "number",
            "title": "Total Revenue",
            "default": 0.0
          },
          "growth_rate": {
            "type": "number",
            "title": "Growth Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "required": [
          "company_id",
          "company_name"
        ],
        "title": "CompanyPerformance",
        "description": "Individual company performance"
      },
      "CompanyResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "subdomain": {
            "type": "string",
            "title": "Subdomain"
          },
          "provider_type": {
            "type": "string",
            "title": "Provider Type"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "webhook_url": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Webhook Url"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          }
        },
        "type": "object",
        "required": [
          "id",
          "name",
          "subdomain",
          "provider_type",
          "is_active",
          "created_at",
          "updated_at"
        ],
        "title": "CompanyResponse",
        "description": "Company response"
      },
      "CompanyUpdateRequest": {
        "properties": {
          "name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Name"
          },
          "settings": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Settings"
          },
          "is_active": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ],
            "title": "Is Active"
          }
        },
        "type": "object",
        "title": "CompanyUpdateRequest",
        "description": "Update company request"
      },
      "ContactCreateRequest": {
        "properties": {
          "first_name": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "email": {
            "anyOf": [
              {
                "type": "string",
                "format": "email"
              },
              {
                "type": "null"
              }
            ],
            "title": "Email"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "position": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Position"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "required": [
          "first_name"
        ],
        "title": "ContactCreateRequest",
        "description": "Create contact request"
      },
      "ContactResponse": {
        "properties": {
          "first_name": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "email": {
            "anyOf": [
              {
                "type": "string",
                "format": "email"
              },
              {
                "type": "null"
              }
            ],
            "title": "Email"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "position": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Position"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "created_by": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Created By"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "total_deals": {
            "type": "integer",
            "title": "Total Deals",
            "default": 0
          },
          "total_calls": {
            "type": "integer",
            "title": "Total Calls",
            "default": 0
          }
        },
        "type": "object",
        "required": [
          "first_name",
          "id",
          "company_id",
          "created_by",
          "created_at",
          "updated_at"
        ],
        "title": "ContactResponse",
        "description": "Contact response"
      },
      "ContactUpdateRequest": {
        "properties": {
          "first_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "email": {
            "anyOf": [
              {
                "type": "string",
                "format": "email"
              },
              {
                "type": "null"
              }
            ],
            "title": "Email"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "position": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Position"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "title": "ContactUpdateRequest",
        "description": "Update contact request"
      },
      "ContractCreateRequest": {
        "properties": {
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "name": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Name"
          },
          "max_admins": {
            "type": "integer",
            "minimum": 1.0,
            "title": "Max Admins",
            "default": 1
          },
          "max_managers": {
            "type": "integer",
            "minimum": 0.0,
            "title": "Max Managers",
            "default": 5
          },
          "max_operators": {
            "type": "integer",
            "minimum": 0.0,
            "title": "Max Operators",
            "default": 10
          },
          "max_storage_gb": {
            "type": "integer",
            "minimum": 1.0,
            "title": "Max Storage Gb",
            "default": 10
          },
          "price": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "string"
              }
            ],
            "title": "Price"
          },
          "currency": {
            "type": "string",
            "maxLength": 3,
            "minLength": 3,
            "title": "Currency",
            "default": "USD"
          },
          "billing_period": {
            "$ref": "#/components/schemas/BillingPeriodEnum",
            "default": "monthly"
          },
          "start_date": {
            "type": "string",
            "format": "date",
            "title": "Start Date"
          },
          "end_date": {
            "type": "string",
            "format": "date",
            "title": "End Date"
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "grace_period_days": {
            "type": "integer",
            "minimum": 0.0,
            "title": "Grace Period Days",
            "default": 30
          },
          "auto_renew": {
            "type": "boolean",
            "title": "Auto Renew",
            "default": false
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Notes"
          },
          "metadata": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Metadata"
          }
        },
        "type": "object",
        "required": [
          "company_id",
          "name",
          "price",
          "start_date",
          "end_date"
        ],
        "title": "ContractCreateRequest",
        "description": "Create a new contract for a company",
        "example": {
          "billing_period": "monthly",
          "company_id": "550e8400-e29b-41d4-a716-446655440000",
          "currency": "USD",
          "end_date": "2025-12-31",
          "max_admins": 2,
          "max_managers": 5,
          "max_operators": 20,
          "max_storage_gb": 50,
          "name": "Standard Plan",
          "price": 99.99,
          "start_date": "2025-01-01"
        }
      },
      "ContractDetailResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "owner_id": {
            "type": "string",
            "format": "uuid",
            "title": "Owner Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "max_admins": {
            "type": "integer",
            "title": "Max Admins"
          },
          "max_managers": {
            "type": "integer",
            "title": "Max Managers"
          },
          "max_operators": {
            "type": "integer",
            "title": "Max Operators"
          },
          "max_storage_gb": {
            "type": "integer",
            "title": "Max Storage Gb"
          },
          "price": {
            "type": "string",
            "title": "Price"
          },
          "currency": {
            "type": "string",
            "title": "Currency"
          },
          "billing_period": {
            "$ref": "#/components/schemas/BillingPeriodEnum"
          },
          "status": {
            "$ref": "#/components/schemas/ContractStatusEnum"
          },
          "payment_status": {
            "$ref": "#/components/schemas/PaymentStatusEnum"
          },
          "start_date": {
            "type": "string",
            "format": "date",
            "title": "Start Date"
          },
          "end_date": {
            "type": "string",
            "format": "date",
            "title": "End Date"
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "grace_period_days": {
            "type": "integer",
            "title": "Grace Period Days"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "auto_renew": {
            "type": "boolean",
            "title": "Auto Renew"
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Notes"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "days_until_expiry": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Days Until Expiry"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "current_admins": {
            "type": "integer",
            "title": "Current Admins",
            "default": 0
          },
          "current_managers": {
            "type": "integer",
            "title": "Current Managers",
            "default": 0
          },
          "current_operators": {
            "type": "integer",
            "title": "Current Operators",
            "default": 0
          }
        },
        "type": "object",
        "required": [
          "id",
          "owner_id",
          "company_id",
          "name",
          "max_admins",
          "max_managers",
          "max_operators",
          "max_storage_gb",
          "price",
          "currency",
          "billing_period",
          "status",
          "payment_status",
          "start_date",
          "end_date",
          "grace_period_days",
          "is_active",
          "auto_renew",
          "created_at",
          "updated_at"
        ],
        "title": "ContractDetailResponse",
        "description": "Detailed contract response with current usage counts"
      },
      "ContractRenewRequest": {
        "properties": {
          "new_end_date": {
            "type": "string",
            "format": "date",
            "title": "New End Date"
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "price": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Price"
          }
        },
        "type": "object",
        "required": [
          "new_end_date"
        ],
        "title": "ContractRenewRequest",
        "description": "Renew an existing contract"
      },
      "ContractResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "owner_id": {
            "type": "string",
            "format": "uuid",
            "title": "Owner Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "max_admins": {
            "type": "integer",
            "title": "Max Admins"
          },
          "max_managers": {
            "type": "integer",
            "title": "Max Managers"
          },
          "max_operators": {
            "type": "integer",
            "title": "Max Operators"
          },
          "max_storage_gb": {
            "type": "integer",
            "title": "Max Storage Gb"
          },
          "price": {
            "type": "string",
            "title": "Price"
          },
          "currency": {
            "type": "string",
            "title": "Currency"
          },
          "billing_period": {
            "$ref": "#/components/schemas/BillingPeriodEnum"
          },
          "status": {
            "$ref": "#/components/schemas/ContractStatusEnum"
          },
          "payment_status": {
            "$ref": "#/components/schemas/PaymentStatusEnum"
          },
          "start_date": {
            "type": "string",
            "format": "date",
            "title": "Start Date"
          },
          "end_date": {
            "type": "string",
            "format": "date",
            "title": "End Date"
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "grace_period_days": {
            "type": "integer",
            "title": "Grace Period Days"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "auto_renew": {
            "type": "boolean",
            "title": "Auto Renew"
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Notes"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "days_until_expiry": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Days Until Expiry"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          }
        },
        "type": "object",
        "required": [
          "id",
          "owner_id",
          "company_id",
          "name",
          "max_admins",
          "max_managers",
          "max_operators",
          "max_storage_gb",
          "price",
          "currency",
          "billing_period",
          "status",
          "payment_status",
          "start_date",
          "end_date",
          "grace_period_days",
          "is_active",
          "auto_renew",
          "created_at",
          "updated_at"
        ],
        "title": "ContractResponse",
        "description": "Standard contract response"
      },
      "ContractStatusEnum": {
        "type": "string",
        "enum": [
          "active",
          "warning",
          "grace_period",
          "expired",
          "suspended",
          "cancelled"
        ],
        "title": "ContractStatusEnum",
        "description": "Contract status enumeration"
      },
      "ContractStatusResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "status": {
            "$ref": "#/components/schemas/ContractStatusEnum"
          },
          "payment_status": {
            "$ref": "#/components/schemas/PaymentStatusEnum"
          },
          "max_admins": {
            "type": "integer",
            "title": "Max Admins"
          },
          "max_managers": {
            "type": "integer",
            "title": "Max Managers"
          },
          "max_operators": {
            "type": "integer",
            "title": "Max Operators"
          },
          "max_storage_gb": {
            "type": "integer",
            "title": "Max Storage Gb"
          },
          "current_admins": {
            "type": "integer",
            "title": "Current Admins",
            "default": 0
          },
          "current_managers": {
            "type": "integer",
            "title": "Current Managers",
            "default": 0
          },
          "current_operators": {
            "type": "integer",
            "title": "Current Operators",
            "default": 0
          },
          "start_date": {
            "type": "string",
            "format": "date",
            "title": "Start Date"
          },
          "end_date": {
            "type": "string",
            "format": "date",
            "title": "End Date"
          },
          "days_until_expiry": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Days Until Expiry"
          },
          "billing_period": {
            "$ref": "#/components/schemas/BillingPeriodEnum"
          },
          "auto_renew": {
            "type": "boolean",
            "title": "Auto Renew"
          },
          "warnings": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "title": "Warnings",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "id",
          "name",
          "status",
          "payment_status",
          "max_admins",
          "max_managers",
          "max_operators",
          "max_storage_gb",
          "start_date",
          "end_date",
          "billing_period",
          "auto_renew"
        ],
        "title": "ContractStatusResponse",
        "description": "Simplified contract view for company users"
      },
      "ContractUpdateRequest": {
        "properties": {
          "name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Name"
          },
          "max_admins": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 1.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Admins"
          },
          "max_managers": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Managers"
          },
          "max_operators": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Operators"
          },
          "max_storage_gb": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 1.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Storage Gb"
          },
          "price": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Price"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 3,
                "minLength": 3
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency"
          },
          "billing_period": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/BillingPeriodEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "status": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ContractStatusEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "payment_status": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PaymentStatusEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "grace_period_days": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Grace Period Days"
          },
          "auto_renew": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ],
            "title": "Auto Renew"
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Notes"
          },
          "metadata": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Metadata"
          }
        },
        "type": "object",
        "title": "ContractUpdateRequest",
        "description": "Update an existing contract"
      },
      "ConversionFunnel": {
        "properties": {
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "contacted": {
            "type": "integer",
            "title": "Contacted",
            "default": 0
          },
          "qualified": {
            "type": "integer",
            "title": "Qualified",
            "default": 0
          },
          "deals_created": {
            "type": "integer",
            "title": "Deals Created",
            "default": 0
          },
          "deals_won": {
            "type": "integer",
            "title": "Deals Won",
            "default": 0
          },
          "contact_rate": {
            "type": "number",
            "title": "Contact Rate",
            "default": 0.0
          },
          "qualification_rate": {
            "type": "number",
            "title": "Qualification Rate",
            "default": 0.0
          },
          "deal_rate": {
            "type": "number",
            "title": "Deal Rate",
            "default": 0.0
          },
          "win_rate": {
            "type": "number",
            "title": "Win Rate",
            "default": 0.0
          },
          "overall_conversion": {
            "type": "number",
            "title": "Overall Conversion",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "ConversionFunnel",
        "description": "Lead conversion funnel"
      },
      "DealCreateRequest": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          },
          "amount": {
            "type": "number",
            "minimum": 0.0,
            "title": "Amount"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency",
            "default": "USD"
          },
          "probability": {
            "anyOf": [
              {
                "type": "integer",
                "maximum": 100.0,
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Probability",
            "default": 0
          },
          "expected_close_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Expected Close Date"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "required": [
          "title",
          "amount"
        ],
        "title": "DealCreateRequest",
        "description": "Create deal request"
      },
      "DealResponse": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          },
          "amount": {
            "type": "number",
            "minimum": 0.0,
            "title": "Amount"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency",
            "default": "USD"
          },
          "probability": {
            "anyOf": [
              {
                "type": "integer",
                "maximum": 100.0,
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Probability",
            "default": 0
          },
          "expected_close_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Expected Close Date"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "stage": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Stage"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          },
          "closed_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Closed Date"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "contact_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Name"
          },
          "assigned_to_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To Name"
          },
          "weighted_value": {
            "type": "number",
            "title": "Weighted Value",
            "default": 0.0
          }
        },
        "type": "object",
        "required": [
          "title",
          "amount",
          "id",
          "company_id",
          "created_at",
          "updated_at"
        ],
        "title": "DealResponse",
        "description": "Deal response"
      },
      "DealStats": {
        "properties": {
          "total_deals": {
            "type": "integer",
            "title": "Total Deals",
            "default": 0
          },
          "prospecting": {
            "type": "integer",
            "title": "Prospecting",
            "default": 0
          },
          "negotiation": {
            "type": "integer",
            "title": "Negotiation",
            "default": 0
          },
          "won": {
            "type": "integer",
            "title": "Won",
            "default": 0
          },
          "lost": {
            "type": "integer",
            "title": "Lost",
            "default": 0
          },
          "total_value": {
            "type": "number",
            "title": "Total Value",
            "default": 0.0
          },
          "won_value": {
            "type": "number",
            "title": "Won Value",
            "default": 0.0
          },
          "average_deal_size": {
            "type": "number",
            "title": "Average Deal Size",
            "default": 0.0
          },
          "win_rate": {
            "type": "number",
            "title": "Win Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "DealStats",
        "description": "Deal statistics"
      },
      "DealUpdateRequest": {
        "properties": {
          "title": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "amount": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Amount"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency"
          },
          "probability": {
            "anyOf": [
              {
                "type": "integer",
                "maximum": 100.0,
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Probability"
          },
          "expected_close_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Expected Close Date"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "title": "DealUpdateRequest",
        "description": "Update deal request"
      },
      "ForgotPasswordRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          }
        },
        "type": "object",
        "required": [
          "email"
        ],
        "title": "ForgotPasswordRequest"
      },
      "HTTPValidationError": {
        "properties": {
          "detail": {
            "items": {
              "$ref": "#/components/schemas/ValidationError"
            },
            "type": "array",
            "title": "Detail"
          }
        },
        "type": "object",
        "title": "HTTPValidationError"
      },
      "InviteAdminRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name"
        ],
        "title": "InviteAdminRequest",
        "description": "Owner invites a superadmin to a company (gets full admin permissions)"
      },
      "LeadCreateRequest": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "estimated_value": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Estimated Value"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency",
            "default": "USD"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "required": [
          "title"
        ],
        "title": "LeadCreateRequest",
        "description": "Create lead request"
      },
      "LeadResponse": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "estimated_value": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Estimated Value"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency",
            "default": "USD"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "status": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Status"
          },
          "pipeline_stage": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Pipeline Stage"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "contact_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Name"
          },
          "assigned_to_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To Name"
          }
        },
        "type": "object",
        "required": [
          "title",
          "id",
          "company_id",
          "created_at",
          "updated_at"
        ],
        "title": "LeadResponse",
        "description": "Lead response"
      },
      "LeadStats": {
        "properties": {
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "new_leads": {
            "type": "integer",
            "title": "New Leads",
            "default": 0
          },
          "contacted_leads": {
            "type": "integer",
            "title": "Contacted Leads",
            "default": 0
          },
          "qualified_leads": {
            "type": "integer",
            "title": "Qualified Leads",
            "default": 0
          },
          "converted_leads": {
            "type": "integer",
            "title": "Converted Leads",
            "default": 0
          },
          "lost_leads": {
            "type": "integer",
            "title": "Lost Leads",
            "default": 0
          },
          "conversion_rate": {
            "type": "number",
            "title": "Conversion Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "LeadStats",
        "description": "Lead statistics"
      },
      "LeadUpdateRequest": {
        "properties": {
          "title": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "estimated_value": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Estimated Value"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "title": "LeadUpdateRequest",
        "description": "Update lead request"
      },
      "LoginRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "password": {
            "type": "string",
            "title": "Password"
          }
        },
        "type": "object",
        "required": [
          "email",
          "password"
        ],
        "title": "LoginRequest"
      },
      "NoteCreateRequest": {
        "properties": {
          "content": {
            "type": "string",
            "minLength": 1,
            "title": "Content"
          },
          "entity_type": {
            "type": "string",
            "maxLength": 50,
            "title": "Entity Type"
          },
          "entity_id": {
            "type": "string",
            "format": "uuid",
            "title": "Entity Id"
          }
        },
        "type": "object",
        "required": [
          "content",
          "entity_type",
          "entity_id"
        ],
        "title": "NoteCreateRequest",
        "description": "Create note request"
      },
      "NoteResponse": {
        "properties": {
          "content": {
            "type": "string",
            "minLength": 1,
            "title": "Content"
          },
          "entity_type": {
            "type": "string",
            "maxLength": 50,
            "title": "Entity Type"
          },
          "entity_id": {
            "type": "string",
            "format": "uuid",
            "title": "Entity Id"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "created_by": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Created By"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "created_by_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Created By Name"
          }
        },
        "type": "object",
        "required": [
          "content",
          "entity_type",
          "entity_id",
          "id",
          "company_id",
          "created_by",
          "created_at",
          "updated_at"
        ],
        "title": "NoteResponse",
        "description": "Note response"
      },
      "NoteUpdateRequest": {
        "properties": {
          "content": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Content"
          }
        },
        "type": "object",
        "title": "NoteUpdateRequest",
        "description": "Update note request"
      },
      "OperatorAnalytics": {
        "properties": {
          "period": {
            "type": "string",
            "title": "Period",
            "description": "today, week, month, year"
          },
          "date_from": {
            "type": "string",
            "format": "date",
            "title": "Date From"
          },
          "date_to": {
            "type": "string",
            "format": "date",
            "title": "Date To"
          },
          "calls": {
            "$ref": "#/components/schemas/CallStats"
          },
          "leads": {
            "$ref": "#/components/schemas/LeadStats"
          },
          "deals": {
            "$ref": "#/components/schemas/DealStats"
          },
          "tasks": {
            "$ref": "#/components/schemas/TaskStats"
          },
          "total_activities": {
            "type": "integer",
            "title": "Total Activities",
            "default": 0
          },
          "productivity_score": {
            "type": "number",
            "title": "Productivity Score",
            "default": 0.0
          }
        },
        "type": "object",
        "required": [
          "period",
          "date_from",
          "date_to",
          "calls",
          "leads",
          "deals",
          "tasks"
        ],
        "title": "OperatorAnalytics",
        "description": "Operator personal analytics"
      },
      "OperatorDashboard": {
        "properties": {
          "today": {
            "$ref": "#/components/schemas/OperatorAnalytics"
          },
          "this_week": {
            "$ref": "#/components/schemas/OperatorAnalytics"
          },
          "this_month": {
            "$ref": "#/components/schemas/OperatorAnalytics"
          },
          "upcoming_tasks": {
            "type": "integer",
            "title": "Upcoming Tasks",
            "default": 0
          },
          "pending_leads": {
            "type": "integer",
            "title": "Pending Leads",
            "default": 0
          },
          "active_deals": {
            "type": "integer",
            "title": "Active Deals",
            "default": 0
          },
          "recent_calls": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Recent Calls",
            "default": []
          },
          "recent_tasks": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Recent Tasks",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "today",
          "this_week",
          "this_month"
        ],
        "title": "OperatorDashboard",
        "description": "Operator dashboard data"
      },
      "OperatorPerformance": {
        "properties": {
          "user_id": {
            "type": "string",
            "title": "User Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "email": {
            "type": "string",
            "title": "Email"
          },
          "calls": {
            "$ref": "#/components/schemas/CallStats"
          },
          "leads": {
            "$ref": "#/components/schemas/LeadStats"
          },
          "deals": {
            "$ref": "#/components/schemas/DealStats"
          },
          "tasks": {
            "$ref": "#/components/schemas/TaskStats"
          },
          "productivity_score": {
            "type": "number",
            "title": "Productivity Score",
            "default": 0.0
          }
        },
        "type": "object",
        "required": [
          "user_id",
          "name",
          "email",
          "calls",
          "leads",
          "deals",
          "tasks"
        ],
        "title": "OperatorPerformance",
        "description": "Individual operator performance"
      },
      "OwnerDashboard": {
        "properties": {
          "today": {
            "$ref": "#/components/schemas/PlatformAnalytics"
          },
          "this_week": {
            "$ref": "#/components/schemas/PlatformAnalytics"
          },
          "this_month": {
            "$ref": "#/components/schemas/PlatformAnalytics"
          },
          "this_year": {
            "$ref": "#/components/schemas/PlatformAnalytics"
          },
          "system_health": {
            "additionalProperties": true,
            "type": "object",
            "title": "System Health",
            "default": {}
          },
          "growth_trend": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Growth Trend",
            "default": []
          },
          "churn_analysis": {
            "additionalProperties": true,
            "type": "object",
            "title": "Churn Analysis",
            "default": {}
          }
        },
        "type": "object",
        "required": [
          "today",
          "this_week",
          "this_month",
          "this_year"
        ],
        "title": "OwnerDashboard",
        "description": "Owner platform dashboard"
      },
      "OwnerLoginRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "password": {
            "type": "string",
            "title": "Password"
          }
        },
        "type": "object",
        "required": [
          "email",
          "password"
        ],
        "title": "OwnerLoginRequest",
        "description": "Owner login request schema"
      },
      "OwnerResponse": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "email_verified": {
            "type": "boolean",
            "title": "Email Verified"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name",
          "id",
          "is_active",
          "email_verified",
          "created_at"
        ],
        "title": "OwnerResponse",
        "description": "Owner response"
      },
      "OwnerWithCredentials": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "email_verified": {
            "type": "boolean",
            "title": "Email Verified"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "must_change_password": {
            "type": "boolean",
            "title": "Must Change Password",
            "default": false
          },
          "credentials": {
            "additionalProperties": true,
            "type": "object",
            "title": "Credentials"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name",
          "id",
          "is_active",
          "email_verified",
          "created_at",
          "credentials"
        ],
        "title": "OwnerWithCredentials",
        "description": "Owner response with JWT credentials"
      },
      "PaginatedResponse": {
        "properties": {
          "items": {
            "items": {},
            "type": "array",
            "title": "Items"
          },
          "total": {
            "type": "integer",
            "title": "Total"
          },
          "page": {
            "type": "integer",
            "title": "Page"
          },
          "page_size": {
            "type": "integer",
            "title": "Page Size"
          },
          "total_pages": {
            "type": "integer",
            "title": "Total Pages"
          }
        },
        "type": "object",
        "required": [
          "items",
          "total",
          "page",
          "page_size",
          "total_pages"
        ],
        "title": "PaginatedResponse",
        "description": "Paginated list response"
      },
      "PaymentStatusEnum": {
        "type": "string",
        "enum": [
          "paid",
          "pending",
          "overdue",
          "failed"
        ],
        "title": "PaymentStatusEnum",
        "description": "Payment status enumeration"
      },
      "PermissionGroupCreateRequest": {
        "properties": {
          "name": {
            "type": "string",
            "maxLength": 100,
            "minLength": 1,
            "title": "Name"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "permissions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "minItems": 1,
            "title": "Permissions",
            "description": "List of permission strings"
          }
        },
        "type": "object",
        "required": [
          "name",
          "permissions"
        ],
        "title": "PermissionGroupCreateRequest",
        "description": "Create a custom permission group"
      },
      "PermissionGroupListResponse": {
        "properties": {
          "groups": {
            "items": {
              "$ref": "#/components/schemas/PermissionGroupResponse"
            },
            "type": "array",
            "title": "Groups"
          },
          "total": {
            "type": "integer",
            "title": "Total"
          }
        },
        "type": "object",
        "required": [
          "groups",
          "total"
        ],
        "title": "PermissionGroupListResponse",
        "description": "Permission group list response"
      },
      "PermissionGroupResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "permissions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "title": "Permissions"
          },
          "is_system": {
            "type": "boolean",
            "title": "Is System"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          }
        },
        "type": "object",
        "required": [
          "id",
          "name",
          "permissions",
          "is_system",
          "created_at",
          "updated_at"
        ],
        "title": "PermissionGroupResponse",
        "description": "Permission group response"
      },
      "PermissionGroupUpdateRequest": {
        "properties": {
          "name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Name"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "permissions": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permissions"
          }
        },
        "type": "object",
        "title": "PermissionGroupUpdateRequest",
        "description": "Update a permission group"
      },
      "PipelineHealth": {
        "properties": {
          "total_value": {
            "type": "number",
            "title": "Total Value",
            "default": 0.0
          },
          "weighted_value": {
            "type": "number",
            "title": "Weighted Value",
            "default": 0.0
          },
          "by_stage": {
            "additionalProperties": true,
            "type": "object",
            "title": "By Stage",
            "default": {}
          },
          "stuck_deals": {
            "type": "integer",
            "title": "Stuck Deals",
            "default": 0
          },
          "forecast": {
            "type": "number",
            "title": "Forecast",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "PipelineHealth",
        "description": "Sales pipeline health"
      },
      "PlatformAnalytics": {
        "properties": {
          "period": {
            "type": "string",
            "title": "Period"
          },
          "date_from": {
            "type": "string",
            "format": "date",
            "title": "Date From"
          },
          "date_to": {
            "type": "string",
            "format": "date",
            "title": "Date To"
          },
          "total_companies": {
            "type": "integer",
            "title": "Total Companies",
            "default": 0
          },
          "active_companies": {
            "type": "integer",
            "title": "Active Companies",
            "default": 0
          },
          "total_users": {
            "type": "integer",
            "title": "Total Users",
            "default": 0
          },
          "active_users": {
            "type": "integer",
            "title": "Active Users",
            "default": 0
          },
          "total_calls": {
            "type": "integer",
            "title": "Total Calls",
            "default": 0
          },
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "total_deals": {
            "type": "integer",
            "title": "Total Deals",
            "default": 0
          },
          "total_revenue": {
            "type": "number",
            "title": "Total Revenue",
            "default": 0.0
          },
          "new_companies": {
            "type": "integer",
            "title": "New Companies",
            "default": 0
          },
          "new_users": {
            "type": "integer",
            "title": "New Users",
            "default": 0
          },
          "revenue_growth": {
            "type": "number",
            "title": "Revenue Growth",
            "default": 0.0
          },
          "top_companies": {
            "items": {
              "$ref": "#/components/schemas/CompanyPerformance"
            },
            "type": "array",
            "title": "Top Companies",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "period",
          "date_from",
          "date_to"
        ],
        "title": "PlatformAnalytics",
        "description": "Platform-wide analytics (for owners)"
      },
      "ProfileUpdateRequest": {
        "properties": {
          "first_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "language": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Language"
          }
        },
        "type": "object",
        "title": "ProfileUpdateRequest",
        "description": "Update own profile (non-admin fields only)"
      },
      "ProviderEnum": {
        "type": "string",
        "enum": [
          "sipuni",
          "binotel"
        ],
        "title": "ProviderEnum",
        "description": "Telephony provider enumeration"
      },
      "RefreshTokenRequest": {
        "properties": {
          "refresh_token": {
            "type": "string",
            "title": "Refresh Token"
          }
        },
        "type": "object",
        "required": [
          "refresh_token"
        ],
        "title": "RefreshTokenRequest",
        "description": "Request body for token refresh"
      },
      "ResetPasswordRequest": {
        "properties": {
          "old_password": {
            "type": "string",
            "minLength": 1,
            "title": "Old Password"
          },
          "new_password": {
            "type": "string",
            "maxLength": 100,
            "minLength": 8,
            "title": "New Password"
          }
        },
        "type": "object",
        "required": [
          "old_password",
          "new_password"
        ],
        "title": "ResetPasswordRequest"
      },
      "SetPasswordRequest": {
        "properties": {
          "token": {
            "type": "string",
            "title": "Token"
          },
          "new_password": {
            "type": "string",
            "maxLength": 100,
            "minLength": 8,
            "title": "New Password"
          }
        },
        "type": "object",
        "required": [
          "token",
          "new_password"
        ],
        "title": "SetPasswordRequest"
      },
      "TaskCreateRequest": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "due_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date-time"
              },
              {
                "type": "null"
              }
            ],
            "title": "Due Date"
          },
          "entity_type": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Type"
          },
          "entity_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Id"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          }
        },
        "type": "object",
        "required": [
          "title"
        ],
        "title": "TaskCreateRequest",
        "description": "Create task request"
      },
      "TaskResponse": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "due_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date-time"
              },
              {
                "type": "null"
              }
            ],
            "title": "Due Date"
          },
          "entity_type": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Type"
          },
          "entity_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Id"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "status": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Status"
          },
          "priority": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Priority"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "created_by": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Created By"
          },
          "completed_at": {
            "anyOf": [
              {
                "type": "string",
                "format": "date-time"
              },
              {
                "type": "null"
              }
            ],
            "title": "Completed At"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "assigned_to_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To Name"
          }
        },
        "type": "object",
        "required": [
          "title",
          "id",
          "company_id",
          "created_at",
          "updated_at"
        ],
        "title": "TaskResponse",
        "description": "Task response"
      },
      "TaskStats": {
        "properties": {
          "total_tasks": {
            "type": "integer",
            "title": "Total Tasks",
            "default": 0
          },
          "pending_tasks": {
            "type": "integer",
            "title": "Pending Tasks",
            "default": 0
          },
          "completed_tasks": {
            "type": "integer",
            "title": "Completed Tasks",
            "default": 0
          },
          "overdue_tasks": {
            "type": "integer",
            "title": "Overdue Tasks",
            "default": 0
          },
          "completion_rate": {
            "type": "number",
            "title": "Completion Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "TaskStats",
        "description": "Task statistics"
      },
      "TaskUpdateRequest": {
        "properties": {
          "title": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Title"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "due_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date-time"
              },
              {
                "type": "null"
              }
            ],
            "title": "Due Date"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "entity_type": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Type"
          },
          "entity_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Id"
          }
        },
        "type": "object",
        "title": "TaskUpdateRequest",
        "description": "Update task request"
      },
      "TeamAnalytics": {
        "properties": {
          "period": {
            "type": "string",
            "title": "Period"
          },
          "date_from": {
            "type": "string",
            "format": "date",
            "title": "Date From"
          },
          "date_to": {
            "type": "string",
            "format": "date",
            "title": "Date To"
          },
          "total_operators": {
            "type": "integer",
            "title": "Total Operators",
            "default": 0
          },
          "active_operators": {
            "type": "integer",
            "title": "Active Operators",
            "default": 0
          },
          "calls": {
            "$ref": "#/components/schemas/CallStats"
          },
          "leads": {
            "$ref": "#/components/schemas/LeadStats"
          },
          "deals": {
            "$ref": "#/components/schemas/DealStats"
          },
          "tasks": {
            "$ref": "#/components/schemas/TaskStats"
          },
          "total_revenue": {
            "type": "number",
            "title": "Total Revenue",
            "default": 0.0
          },
          "revenue_growth": {
            "type": "number",
            "title": "Revenue Growth",
            "default": 0.0
          },
          "top_operators_by_calls": {
            "items": {
              "$ref": "#/components/schemas/OperatorPerformance"
            },
            "type": "array",
            "title": "Top Operators By Calls",
            "default": []
          },
          "top_operators_by_deals": {
            "items": {
              "$ref": "#/components/schemas/OperatorPerformance"
            },
            "type": "array",
            "title": "Top Operators By Deals",
            "default": []
          },
          "top_operators_by_revenue": {
            "items": {
              "$ref": "#/components/schemas/OperatorPerformance"
            },
            "type": "array",
            "title": "Top Operators By Revenue",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "period",
          "date_from",
          "date_to",
          "calls",
          "leads",
          "deals",
          "tasks"
        ],
        "title": "TeamAnalytics",
        "description": "Team-wide analytics (for admins)"
      },
      "UserDetailResponse": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Id"
          },
          "role": {
            "type": "string",
            "title": "Role"
          },
          "permissions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "title": "Permissions"
          },
          "permission_group_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permission Group Id"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "is_suspended": {
            "type": "boolean",
            "title": "Is Suspended"
          },
          "email_verified": {
            "type": "boolean",
            "title": "Email Verified"
          },
          "language": {
            "type": "string",
            "title": "Language"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "total_calls": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Total Calls",
            "default": 0
          },
          "total_leads": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Total Leads",
            "default": 0
          },
          "total_deals": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Total Deals",
            "default": 0
          },
          "total_tasks": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Total Tasks",
            "default": 0
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name",
          "id",
          "company_id",
          "role",
          "permissions",
          "is_active",
          "is_suspended",
          "email_verified",
          "language",
          "created_at"
        ],
        "title": "UserDetailResponse",
        "description": "Detailed user response with stats"
      },
      "UserInviteRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "role": {
            "type": "string",
            "title": "Role",
            "description": "Role: company_admin or company_operator",
            "default": "company_operator"
          },
          "permissions": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permissions",
            "description": "Custom permissions"
          },
          "permission_group_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permission Group Id",
            "description": "Permission group to assign"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name"
        ],
        "title": "UserInviteRequest",
        "description": "Admin invites operator via email"
      },
      "UserListResponse": {
        "properties": {
          "users": {
            "items": {
              "$ref": "#/components/schemas/UserResponse"
            },
            "type": "array",
            "title": "Users"
          },
          "total": {
            "type": "integer",
            "title": "Total"
          },
          "page": {
            "type": "integer",
            "title": "Page"
          },
          "page_size": {
            "type": "integer",
            "title": "Page Size"
          }
        },
        "type": "object",
        "required": [
          "users",
          "total",
          "page",
          "page_size"
        ],
        "title": "UserListResponse",
        "description": "Paginated user list"
      },
      "UserResponse": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Id"
          },
          "role": {
            "type": "string",
            "title": "Role"
          },
          "permissions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "title": "Permissions"
          },
          "permission_group_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permission Group Id"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "is_suspended": {
            "type": "boolean",
            "title": "Is Suspended"
          },
          "email_verified": {
            "type": "boolean",
            "title": "Email Verified"
          },
          "language": {
            "type": "string",
            "title": "Language"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name",
          "id",
          "company_id",
          "role",
          "permissions",
          "is_active",
          "is_suspended",
          "email_verified",
          "language",
          "created_at"
        ],
        "title": "UserResponse",
        "description": "User response"
      },
      "UserUpdateRequest": {
        "properties": {
          "first_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "is_active": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ],
            "title": "Is Active"
          },
          "is_suspended": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ],
            "title": "Is Suspended"
          },
          "role": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Role"
          },
          "permissions": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permissions"
          },
          "permission_group_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permission Group Id",
            "description": "Permission group to assign"
          }
        },
        "type": "object",
        "title": "UserUpdateRequest",
        "description": "Update user information"
      },
      "ValidationError": {
        "properties": {
          "loc": {
            "items": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "integer"
                }
              ]
            },
            "type": "array",
            "title": "Location"
          },
          "msg": {
            "type": "string",
            "title": "Message"
          },
          "type": {
            "type": "string",
            "title": "Error Type"
          }
        },
        "type": "object",
        "required": [
          "loc",
          "msg",
          "type"
        ],
        "title": "ValidationError"
      }
    },
    "securitySchemes": {
      "HTTPBearer": {
        "type": "http",
        "scheme": "bearer"
      }
    }
  }
}
```

</details>

---

## 5. API Endpoints — Owner API

Full OpenAPI 3.1.0 specification for the Owner API (`/api/v1/owner/*`):

<details>
<summary>Click to expand Owner API OpenAPI JSON</summary>

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "S1P - Owner API",
    "version": "0.1.0"
  },
  "paths": {
    "/api/v1/owner/auth/login": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Auth"
        ],
        "summary": "Login Owner",
        "description": "Owner login\n\nReturns JWT tokens for authenticated owner.\nIf the owner has a temporary password, returns a restricted token\nthat only works with set-password.",
        "operationId": "login_owner_api_v1_owner_auth_login_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/OwnerLoginRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/auth/me": {
      "get": {
        "tags": [
          "Owner Operations",
          "Owner Auth"
        ],
        "summary": "Get Current Owner",
        "description": "Get current owner profile\n\nRequires authentication via JWT token.",
        "operationId": "get_current_owner_api_v1_owner_auth_me_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OwnerResponse"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/owner/auth/reset-password": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Auth"
        ],
        "summary": "Reset Password",
        "description": "Reset owner password (authenticated owner who knows their current password).\n\nRequires old password for verification.",
        "operationId": "reset_password_api_v1_owner_auth_reset_password_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ResetPasswordRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/owner/auth/forgot-password": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Auth"
        ],
        "summary": "Forgot Password",
        "description": "Request a password reset email for owner.\n\nAlways returns 200 to prevent email enumeration.",
        "operationId": "forgot_password_api_v1_owner_auth_forgot_password_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ForgotPasswordRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/auth/set-password": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Auth"
        ],
        "summary": "Set Password",
        "description": "Set new owner password using a temporary token.\n\nWorks for both flows:\n- First login: token from login response (purpose=set_password)\n- Forgot password: token from reset email (purpose=owner_password_reset)\n\nReturns full access/refresh credentials on success.",
        "operationId": "set_password_api_v1_owner_auth_set_password_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/SetPasswordRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OwnerWithCredentials"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/companies": {
      "get": {
        "tags": [
          "Owner Operations",
          "Owner Company Management"
        ],
        "summary": "List Companies",
        "description": "List all companies owned by the current owner\n\nReturns a list of all companies with basic information.",
        "operationId": "list_companies_api_v1_owner_companies_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "items": {
                    "$ref": "#/components/schemas/CompanyResponse"
                  },
                  "type": "array",
                  "title": "Response List Companies Api V1 Owner Companies Get"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      },
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Company Management"
        ],
        "summary": "Create Company",
        "description": "Create a new company\n\nOnly owners can create companies. The owner selects the telephony provider\n(Sipuni or Binotel) and provides the provider configuration.\n\nThe provider cannot be changed after company creation.",
        "operationId": "create_company_api_v1_owner_companies_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/CompanyCreateRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CompanyDetailResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/owner/companies/{company_id}/invite-admin": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Company Management"
        ],
        "summary": "Invite Admin",
        "description": "Invite a superadmin to a company (Owner only)\n\nCreates a COMPANY_ADMIN user with full admin permissions\nand sends an email invitation with a temporary password.",
        "operationId": "invite_admin_api_v1_owner_companies__company_id__invite_admin_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "company_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Company Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/InviteAdminRequest"
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/companies/{company_id}": {
      "get": {
        "tags": [
          "Owner Operations",
          "Owner Company Management"
        ],
        "summary": "Get Company",
        "description": "Get detailed information about a specific company\n\nIncludes provider configuration and settings.",
        "operationId": "get_company_api_v1_owner_companies__company_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "company_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Company Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CompanyDetailResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Owner Operations",
          "Owner Company Management"
        ],
        "summary": "Update Company",
        "description": "Update company information\n\nCan update name, settings, and active status.\nProvider type and configuration cannot be changed.",
        "operationId": "update_company_api_v1_owner_companies__company_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "company_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Company Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/CompanyUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CompanyResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "delete": {
        "tags": [
          "Owner Operations",
          "Owner Company Management"
        ],
        "summary": "Delete Company",
        "description": "Delete a company\n\nBy default performs soft delete (can be restored).\nUse hard=true for permanent deletion.",
        "operationId": "delete_company_api_v1_owner_companies__company_id__delete",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "company_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Company Id"
            }
          },
          {
            "name": "hard",
            "in": "query",
            "required": false,
            "schema": {
              "type": "boolean",
              "default": false,
              "title": "Hard"
            }
          }
        ],
        "responses": {
          "204": {
            "description": "Successful Response"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/companies/{company_id}/activate": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Company Management"
        ],
        "summary": "Activate Company",
        "description": "Activate a suspended company",
        "operationId": "activate_company_api_v1_owner_companies__company_id__activate_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "company_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Company Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CompanyResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/companies/{company_id}/deactivate": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Company Management"
        ],
        "summary": "Deactivate Company",
        "description": "Deactivate a company (suspend access)",
        "operationId": "deactivate_company_api_v1_owner_companies__company_id__deactivate_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "company_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Company Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/CompanyResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/contracts": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Contract Management"
        ],
        "summary": "Create Contract",
        "description": "Create a contract for a company.\n\nValidates company ownership and ensures no duplicate active contracts.",
        "operationId": "create_contract_api_v1_owner_contracts_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ContractCreateRequest"
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContractDetailResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "get": {
        "tags": [
          "Owner Operations",
          "Owner Contract Management"
        ],
        "summary": "List Contracts",
        "description": "List all contracts owned by the current owner, with optional filters.",
        "operationId": "list_contracts_api_v1_owner_contracts_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "company_id",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "uuid"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Company Id"
            }
          },
          {
            "name": "status",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "$ref": "#/components/schemas/ContractStatusEnum"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Status"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "type": "array",
                  "items": {
                    "$ref": "#/components/schemas/ContractResponse"
                  },
                  "title": "Response List Contracts Api V1 Owner Contracts Get"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/contracts/{contract_id}": {
      "get": {
        "tags": [
          "Owner Operations",
          "Owner Contract Management"
        ],
        "summary": "Get Contract",
        "description": "Get detailed contract information with current usage counts.",
        "operationId": "get_contract_api_v1_owner_contracts__contract_id__get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "contract_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Contract Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContractDetailResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      },
      "put": {
        "tags": [
          "Owner Operations",
          "Owner Contract Management"
        ],
        "summary": "Update Contract",
        "description": "Update contract limits, pricing, or payment status.",
        "operationId": "update_contract_api_v1_owner_contracts__contract_id__put",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "contract_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Contract Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ContractUpdateRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContractResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/contracts/{contract_id}/renew": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Contract Management"
        ],
        "summary": "Renew Contract",
        "description": "Renew a contract: reset status to ACTIVE and extend end_date.",
        "operationId": "renew_contract_api_v1_owner_contracts__contract_id__renew_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "contract_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Contract Id"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/ContractRenewRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContractResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/contracts/{contract_id}/cancel": {
      "post": {
        "tags": [
          "Owner Operations",
          "Owner Contract Management"
        ],
        "summary": "Cancel Contract",
        "description": "Cancel a contract.",
        "operationId": "cancel_contract_api_v1_owner_contracts__contract_id__cancel_post",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "contract_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "format": "uuid",
              "title": "Contract Id"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ContractResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/analytics/platform": {
      "get": {
        "tags": [
          "Owner Operations",
          "Owner Analytics"
        ],
        "summary": "Get Platform Analytics",
        "description": "Get platform-wide analytics (Owner only)\n\nOPTIMIZED:\n- Single query for company/user counts\n- Aggregated stats across all companies (not N queries)\n- Top companies ranked in single query",
        "operationId": "get_platform_analytics_api_v1_owner_analytics_platform_get",
        "security": [
          {
            "HTTPBearer": []
          }
        ],
        "parameters": [
          {
            "name": "period",
            "in": "query",
            "required": false,
            "schema": {
              "type": "string",
              "description": "today, week, month, year",
              "default": "month",
              "title": "Period"
            },
            "description": "today, week, month, year"
          },
          {
            "name": "date_from",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date From"
            }
          },
          {
            "name": "date_to",
            "in": "query",
            "required": false,
            "schema": {
              "anyOf": [
                {
                  "type": "string",
                  "format": "date"
                },
                {
                  "type": "null"
                }
              ],
              "title": "Date To"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/PlatformAnalytics"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v1/owner/analytics/dashboard": {
      "get": {
        "tags": [
          "Owner Operations",
          "Owner Analytics"
        ],
        "summary": "Get Owner Dashboard",
        "description": "Get owner dashboard (Owner only)\n\nOPTIMIZED:\n- Caching with 5 minute TTL\n- Aggregated queries across all companies\n- Single queries for trends",
        "operationId": "get_owner_dashboard_api_v1_owner_analytics_dashboard_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OwnerDashboard"
                }
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/owner/analytics/cache": {
      "delete": {
        "tags": [
          "Owner Operations",
          "Owner Analytics"
        ],
        "summary": "Clear Owner Cache",
        "description": "Clear owner analytics cache\n\nUse this after bulk data imports or when you need fresh data.",
        "operationId": "clear_owner_cache_api_v1_owner_analytics_cache_delete",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    },
    "/api/v1/owner/permissions": {
      "get": {
        "tags": [
          "Owner Operations",
          "Permissions"
        ],
        "summary": "List Permissions",
        "description": "List all available permissions and default permissions per role\n\nReturns every permission constant and the default set for each company role.",
        "operationId": "list_permissions_api_v1_owner_permissions_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          }
        },
        "security": [
          {
            "HTTPBearer": []
          }
        ]
      }
    }
  },
  "components": {
    "schemas": {
      "AdminDashboard": {
        "properties": {
          "today": {
            "$ref": "#/components/schemas/TeamAnalytics"
          },
          "this_week": {
            "$ref": "#/components/schemas/TeamAnalytics"
          },
          "this_month": {
            "$ref": "#/components/schemas/TeamAnalytics"
          },
          "this_year": {
            "$ref": "#/components/schemas/TeamAnalytics"
          },
          "conversion_funnel": {
            "$ref": "#/components/schemas/ConversionFunnel"
          },
          "pipeline_health": {
            "$ref": "#/components/schemas/PipelineHealth"
          },
          "peak_call_hours": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Peak Call Hours",
            "default": []
          },
          "calls_trend": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Calls Trend",
            "default": []
          },
          "revenue_trend": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Revenue Trend",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "today",
          "this_week",
          "this_month",
          "this_year",
          "conversion_funnel",
          "pipeline_health"
        ],
        "title": "AdminDashboard",
        "description": "Admin dashboard data"
      },
      "AuthorizedResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "first_name": {
            "type": "string",
            "maxLength": 255,
            "title": "First Name"
          },
          "last_name": {
            "type": "string",
            "maxLength": 255,
            "title": "Last Name"
          },
          "email": {
            "type": "string",
            "maxLength": 2048,
            "title": "Email"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "must_change_password": {
            "type": "boolean",
            "title": "Must Change Password",
            "default": false
          },
          "credentials": {
            "$ref": "#/components/schemas/BearerToken"
          }
        },
        "type": "object",
        "required": [
          "id",
          "first_name",
          "last_name",
          "email",
          "is_active",
          "credentials"
        ],
        "title": "AuthorizedResponse"
      },
      "BearerToken": {
        "properties": {
          "type": {
            "type": "string",
            "title": "Type",
            "default": "Bearer"
          },
          "access": {
            "type": "string",
            "title": "Access"
          },
          "refresh": {
            "type": "string",
            "title": "Refresh"
          }
        },
        "type": "object",
        "required": [
          "access",
          "refresh"
        ],
        "title": "BearerToken"
      },
      "BillingPeriodEnum": {
        "type": "string",
        "enum": [
          "monthly",
          "yearly"
        ],
        "title": "BillingPeriodEnum",
        "description": "Billing period enumeration"
      },
      "CallDirectionEnum": {
        "type": "string",
        "enum": [
          "inbound",
          "outbound",
          "internal"
        ],
        "title": "CallDirectionEnum",
        "description": "Call direction enumeration"
      },
      "CallEventResponse": {
        "properties": {
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "provider_type": {
            "$ref": "#/components/schemas/ProviderEnum"
          },
          "provider_call_id": {
            "type": "string",
            "title": "Provider Call Id"
          },
          "phone_1": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone 1"
          },
          "phone_2": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone 2"
          },
          "operator_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Operator Id"
          },
          "direction": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/CallDirectionEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "state": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/CallStatusEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "attempts": {
            "type": "integer",
            "title": "Attempts"
          },
          "waiting_sec": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Waiting Sec"
          },
          "billing_sec": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Billing Sec"
          },
          "record_url": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Record Url"
          },
          "call_start_timestamp": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Call Start Timestamp"
          },
          "call_end_timestamp": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Call End Timestamp"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          }
        },
        "type": "object",
        "required": [
          "created_at",
          "updated_at",
          "id",
          "company_id",
          "provider_type",
          "provider_call_id",
          "attempts"
        ],
        "title": "CallEventResponse",
        "description": "Call event response"
      },
      "CallLinkRequest": {
        "properties": {
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          },
          "deal_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Deal Id"
          }
        },
        "type": "object",
        "title": "CallLinkRequest",
        "description": "Link call to CRM entities"
      },
      "CallOutcomeUpdate": {
        "properties": {
          "outcome": {
            "type": "string",
            "title": "Outcome",
            "description": "Call outcome"
          },
          "disposition_notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Disposition Notes",
            "description": "Notes about the call"
          }
        },
        "type": "object",
        "required": [
          "outcome"
        ],
        "title": "CallOutcomeUpdate",
        "description": "Update call outcome"
      },
      "CallRecordingURL": {
        "properties": {
          "url": {
            "type": "string",
            "title": "Url"
          },
          "expires_in": {
            "type": "integer",
            "title": "Expires In"
          }
        },
        "type": "object",
        "required": [
          "url",
          "expires_in"
        ],
        "title": "CallRecordingURL",
        "description": "Call recording URL response"
      },
      "CallRequest": {
        "properties": {
          "phone_1": {
            "type": "string",
            "title": "Phone 1",
            "description": "First phone number (caller or external)"
          },
          "phone_2": {
            "type": "string",
            "title": "Phone 2",
            "description": "Second phone number (receiver or internal)"
          },
          "operator_id": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Operator Id",
            "description": "Operator identifier: UUID, phone, email, or SIP extension (e.g. '100001'). For Sipuni, this is the internal SIP number and is required."
          },
          "order_id": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Order Id",
            "description": "External order/ticket ID"
          },
          "utm_source": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Utm Source"
          },
          "utm_medium": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Utm Medium"
          },
          "utm_campaign": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Utm Campaign"
          }
        },
        "type": "object",
        "required": [
          "phone_1",
          "phone_2"
        ],
        "title": "CallRequest",
        "description": "Request to initiate a call"
      },
      "CallResponse": {
        "properties": {
          "success": {
            "type": "boolean",
            "title": "Success"
          },
          "call_id": {
            "type": "string",
            "title": "Call Id",
            "description": "Provider's call ID"
          },
          "message": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Message"
          },
          "error": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Error"
          }
        },
        "type": "object",
        "required": [
          "success",
          "call_id"
        ],
        "title": "CallResponse",
        "description": "Response from call initiation"
      },
      "CallStats": {
        "properties": {
          "total_calls": {
            "type": "integer",
            "title": "Total Calls",
            "default": 0
          },
          "answered_calls": {
            "type": "integer",
            "title": "Answered Calls",
            "default": 0
          },
          "missed_calls": {
            "type": "integer",
            "title": "Missed Calls",
            "default": 0
          },
          "outbound_calls": {
            "type": "integer",
            "title": "Outbound Calls",
            "default": 0
          },
          "inbound_calls": {
            "type": "integer",
            "title": "Inbound Calls",
            "default": 0
          },
          "total_duration": {
            "type": "integer",
            "title": "Total Duration",
            "default": 0
          },
          "average_duration": {
            "type": "number",
            "title": "Average Duration",
            "default": 0.0
          },
          "success_rate": {
            "type": "number",
            "title": "Success Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "CallStats",
        "description": "Call statistics"
      },
      "CallStatusEnum": {
        "type": "string",
        "enum": [
          "ANSWER",
          "BUSY",
          "NOANSWER",
          "CANCEL",
          "CONGESTION",
          "CHANUNAVAIL"
        ],
        "title": "CallStatusEnum",
        "description": "Call status enumeration"
      },
      "CompanyCreateRequest": {
        "properties": {
          "name": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Name"
          },
          "subdomain": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Subdomain",
            "description": "Company subdomain (auto-generated if not provided)"
          },
          "provider_type": {
            "type": "string",
            "title": "Provider Type",
            "description": "Provider: sipuni or binotel"
          },
          "provider_config": {
            "additionalProperties": true,
            "type": "object",
            "title": "Provider Config",
            "description": "Provider-specific configuration (requires cabinet_id and security_key)"
          },
          "settings": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Settings"
          }
        },
        "type": "object",
        "required": [
          "name",
          "provider_type",
          "provider_config"
        ],
        "title": "CompanyCreateRequest",
        "description": "Create company request",
        "example": {
          "name": "My Company LLC",
          "provider_config": {
            "cabinet_id": "12345",
            "security_key": "your-secret-key"
          },
          "provider_type": "sipuni",
          "settings": {
            "language": "ru",
            "timezone": "Asia/Tashkent"
          },
          "subdomain": "mycompany"
        }
      },
      "CompanyDetailResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "subdomain": {
            "type": "string",
            "title": "Subdomain"
          },
          "provider_type": {
            "type": "string",
            "title": "Provider Type"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "webhook_url": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Webhook Url"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "provider_config": {
            "additionalProperties": true,
            "type": "object",
            "title": "Provider Config"
          },
          "settings": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Settings"
          },
          "webhook_token": {
            "type": "string",
            "title": "Webhook Token"
          }
        },
        "type": "object",
        "required": [
          "id",
          "name",
          "subdomain",
          "provider_type",
          "is_active",
          "created_at",
          "updated_at",
          "provider_config",
          "webhook_token"
        ],
        "title": "CompanyDetailResponse",
        "description": "Detailed company response with config"
      },
      "CompanyPerformance": {
        "properties": {
          "company_id": {
            "type": "string",
            "title": "Company Id"
          },
          "company_name": {
            "type": "string",
            "title": "Company Name"
          },
          "total_users": {
            "type": "integer",
            "title": "Total Users",
            "default": 0
          },
          "active_users": {
            "type": "integer",
            "title": "Active Users",
            "default": 0
          },
          "total_calls": {
            "type": "integer",
            "title": "Total Calls",
            "default": 0
          },
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "total_deals": {
            "type": "integer",
            "title": "Total Deals",
            "default": 0
          },
          "total_revenue": {
            "type": "number",
            "title": "Total Revenue",
            "default": 0.0
          },
          "growth_rate": {
            "type": "number",
            "title": "Growth Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "required": [
          "company_id",
          "company_name"
        ],
        "title": "CompanyPerformance",
        "description": "Individual company performance"
      },
      "CompanyResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "subdomain": {
            "type": "string",
            "title": "Subdomain"
          },
          "provider_type": {
            "type": "string",
            "title": "Provider Type"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "webhook_url": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Webhook Url"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          }
        },
        "type": "object",
        "required": [
          "id",
          "name",
          "subdomain",
          "provider_type",
          "is_active",
          "created_at",
          "updated_at"
        ],
        "title": "CompanyResponse",
        "description": "Company response"
      },
      "CompanyUpdateRequest": {
        "properties": {
          "name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Name"
          },
          "settings": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Settings"
          },
          "is_active": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ],
            "title": "Is Active"
          }
        },
        "type": "object",
        "title": "CompanyUpdateRequest",
        "description": "Update company request"
      },
      "ContactCreateRequest": {
        "properties": {
          "first_name": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "email": {
            "anyOf": [
              {
                "type": "string",
                "format": "email"
              },
              {
                "type": "null"
              }
            ],
            "title": "Email"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "position": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Position"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "required": [
          "first_name"
        ],
        "title": "ContactCreateRequest",
        "description": "Create contact request"
      },
      "ContactResponse": {
        "properties": {
          "first_name": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "email": {
            "anyOf": [
              {
                "type": "string",
                "format": "email"
              },
              {
                "type": "null"
              }
            ],
            "title": "Email"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "position": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Position"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "created_by": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Created By"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "total_deals": {
            "type": "integer",
            "title": "Total Deals",
            "default": 0
          },
          "total_calls": {
            "type": "integer",
            "title": "Total Calls",
            "default": 0
          }
        },
        "type": "object",
        "required": [
          "first_name",
          "id",
          "company_id",
          "created_by",
          "created_at",
          "updated_at"
        ],
        "title": "ContactResponse",
        "description": "Contact response"
      },
      "ContactUpdateRequest": {
        "properties": {
          "first_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "email": {
            "anyOf": [
              {
                "type": "string",
                "format": "email"
              },
              {
                "type": "null"
              }
            ],
            "title": "Email"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "position": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255
              },
              {
                "type": "null"
              }
            ],
            "title": "Position"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "title": "ContactUpdateRequest",
        "description": "Update contact request"
      },
      "ContractCreateRequest": {
        "properties": {
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "name": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Name"
          },
          "max_admins": {
            "type": "integer",
            "minimum": 1.0,
            "title": "Max Admins",
            "default": 1
          },
          "max_managers": {
            "type": "integer",
            "minimum": 0.0,
            "title": "Max Managers",
            "default": 5
          },
          "max_operators": {
            "type": "integer",
            "minimum": 0.0,
            "title": "Max Operators",
            "default": 10
          },
          "max_storage_gb": {
            "type": "integer",
            "minimum": 1.0,
            "title": "Max Storage Gb",
            "default": 10
          },
          "price": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "string"
              }
            ],
            "title": "Price"
          },
          "currency": {
            "type": "string",
            "maxLength": 3,
            "minLength": 3,
            "title": "Currency",
            "default": "USD"
          },
          "billing_period": {
            "$ref": "#/components/schemas/BillingPeriodEnum",
            "default": "monthly"
          },
          "start_date": {
            "type": "string",
            "format": "date",
            "title": "Start Date"
          },
          "end_date": {
            "type": "string",
            "format": "date",
            "title": "End Date"
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "grace_period_days": {
            "type": "integer",
            "minimum": 0.0,
            "title": "Grace Period Days",
            "default": 30
          },
          "auto_renew": {
            "type": "boolean",
            "title": "Auto Renew",
            "default": false
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Notes"
          },
          "metadata": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Metadata"
          }
        },
        "type": "object",
        "required": [
          "company_id",
          "name",
          "price",
          "start_date",
          "end_date"
        ],
        "title": "ContractCreateRequest",
        "description": "Create a new contract for a company",
        "example": {
          "billing_period": "monthly",
          "company_id": "550e8400-e29b-41d4-a716-446655440000",
          "currency": "USD",
          "end_date": "2025-12-31",
          "max_admins": 2,
          "max_managers": 5,
          "max_operators": 20,
          "max_storage_gb": 50,
          "name": "Standard Plan",
          "price": 99.99,
          "start_date": "2025-01-01"
        }
      },
      "ContractDetailResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "owner_id": {
            "type": "string",
            "format": "uuid",
            "title": "Owner Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "max_admins": {
            "type": "integer",
            "title": "Max Admins"
          },
          "max_managers": {
            "type": "integer",
            "title": "Max Managers"
          },
          "max_operators": {
            "type": "integer",
            "title": "Max Operators"
          },
          "max_storage_gb": {
            "type": "integer",
            "title": "Max Storage Gb"
          },
          "price": {
            "type": "string",
            "title": "Price"
          },
          "currency": {
            "type": "string",
            "title": "Currency"
          },
          "billing_period": {
            "$ref": "#/components/schemas/BillingPeriodEnum"
          },
          "status": {
            "$ref": "#/components/schemas/ContractStatusEnum"
          },
          "payment_status": {
            "$ref": "#/components/schemas/PaymentStatusEnum"
          },
          "start_date": {
            "type": "string",
            "format": "date",
            "title": "Start Date"
          },
          "end_date": {
            "type": "string",
            "format": "date",
            "title": "End Date"
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "grace_period_days": {
            "type": "integer",
            "title": "Grace Period Days"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "auto_renew": {
            "type": "boolean",
            "title": "Auto Renew"
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Notes"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "days_until_expiry": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Days Until Expiry"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "current_admins": {
            "type": "integer",
            "title": "Current Admins",
            "default": 0
          },
          "current_managers": {
            "type": "integer",
            "title": "Current Managers",
            "default": 0
          },
          "current_operators": {
            "type": "integer",
            "title": "Current Operators",
            "default": 0
          }
        },
        "type": "object",
        "required": [
          "id",
          "owner_id",
          "company_id",
          "name",
          "max_admins",
          "max_managers",
          "max_operators",
          "max_storage_gb",
          "price",
          "currency",
          "billing_period",
          "status",
          "payment_status",
          "start_date",
          "end_date",
          "grace_period_days",
          "is_active",
          "auto_renew",
          "created_at",
          "updated_at"
        ],
        "title": "ContractDetailResponse",
        "description": "Detailed contract response with current usage counts"
      },
      "ContractRenewRequest": {
        "properties": {
          "new_end_date": {
            "type": "string",
            "format": "date",
            "title": "New End Date"
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "price": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Price"
          }
        },
        "type": "object",
        "required": [
          "new_end_date"
        ],
        "title": "ContractRenewRequest",
        "description": "Renew an existing contract"
      },
      "ContractResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "owner_id": {
            "type": "string",
            "format": "uuid",
            "title": "Owner Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "max_admins": {
            "type": "integer",
            "title": "Max Admins"
          },
          "max_managers": {
            "type": "integer",
            "title": "Max Managers"
          },
          "max_operators": {
            "type": "integer",
            "title": "Max Operators"
          },
          "max_storage_gb": {
            "type": "integer",
            "title": "Max Storage Gb"
          },
          "price": {
            "type": "string",
            "title": "Price"
          },
          "currency": {
            "type": "string",
            "title": "Currency"
          },
          "billing_period": {
            "$ref": "#/components/schemas/BillingPeriodEnum"
          },
          "status": {
            "$ref": "#/components/schemas/ContractStatusEnum"
          },
          "payment_status": {
            "$ref": "#/components/schemas/PaymentStatusEnum"
          },
          "start_date": {
            "type": "string",
            "format": "date",
            "title": "Start Date"
          },
          "end_date": {
            "type": "string",
            "format": "date",
            "title": "End Date"
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "grace_period_days": {
            "type": "integer",
            "title": "Grace Period Days"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "auto_renew": {
            "type": "boolean",
            "title": "Auto Renew"
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Notes"
          },
          "company_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Name"
          },
          "days_until_expiry": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Days Until Expiry"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          }
        },
        "type": "object",
        "required": [
          "id",
          "owner_id",
          "company_id",
          "name",
          "max_admins",
          "max_managers",
          "max_operators",
          "max_storage_gb",
          "price",
          "currency",
          "billing_period",
          "status",
          "payment_status",
          "start_date",
          "end_date",
          "grace_period_days",
          "is_active",
          "auto_renew",
          "created_at",
          "updated_at"
        ],
        "title": "ContractResponse",
        "description": "Standard contract response"
      },
      "ContractStatusEnum": {
        "type": "string",
        "enum": [
          "active",
          "warning",
          "grace_period",
          "expired",
          "suspended",
          "cancelled"
        ],
        "title": "ContractStatusEnum",
        "description": "Contract status enumeration"
      },
      "ContractStatusResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "status": {
            "$ref": "#/components/schemas/ContractStatusEnum"
          },
          "payment_status": {
            "$ref": "#/components/schemas/PaymentStatusEnum"
          },
          "max_admins": {
            "type": "integer",
            "title": "Max Admins"
          },
          "max_managers": {
            "type": "integer",
            "title": "Max Managers"
          },
          "max_operators": {
            "type": "integer",
            "title": "Max Operators"
          },
          "max_storage_gb": {
            "type": "integer",
            "title": "Max Storage Gb"
          },
          "current_admins": {
            "type": "integer",
            "title": "Current Admins",
            "default": 0
          },
          "current_managers": {
            "type": "integer",
            "title": "Current Managers",
            "default": 0
          },
          "current_operators": {
            "type": "integer",
            "title": "Current Operators",
            "default": 0
          },
          "start_date": {
            "type": "string",
            "format": "date",
            "title": "Start Date"
          },
          "end_date": {
            "type": "string",
            "format": "date",
            "title": "End Date"
          },
          "days_until_expiry": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Days Until Expiry"
          },
          "billing_period": {
            "$ref": "#/components/schemas/BillingPeriodEnum"
          },
          "auto_renew": {
            "type": "boolean",
            "title": "Auto Renew"
          },
          "warnings": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "title": "Warnings",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "id",
          "name",
          "status",
          "payment_status",
          "max_admins",
          "max_managers",
          "max_operators",
          "max_storage_gb",
          "start_date",
          "end_date",
          "billing_period",
          "auto_renew"
        ],
        "title": "ContractStatusResponse",
        "description": "Simplified contract view for company users"
      },
      "ContractUpdateRequest": {
        "properties": {
          "name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Name"
          },
          "max_admins": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 1.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Admins"
          },
          "max_managers": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Managers"
          },
          "max_operators": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Operators"
          },
          "max_storage_gb": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 1.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Max Storage Gb"
          },
          "price": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Price"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 3,
                "minLength": 3
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency"
          },
          "billing_period": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/BillingPeriodEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "status": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/ContractStatusEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "payment_status": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/PaymentStatusEnum"
              },
              {
                "type": "null"
              }
            ]
          },
          "next_payment_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Next Payment Date"
          },
          "grace_period_days": {
            "anyOf": [
              {
                "type": "integer",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Grace Period Days"
          },
          "auto_renew": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ],
            "title": "Auto Renew"
          },
          "notes": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Notes"
          },
          "metadata": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Metadata"
          }
        },
        "type": "object",
        "title": "ContractUpdateRequest",
        "description": "Update an existing contract"
      },
      "ConversionFunnel": {
        "properties": {
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "contacted": {
            "type": "integer",
            "title": "Contacted",
            "default": 0
          },
          "qualified": {
            "type": "integer",
            "title": "Qualified",
            "default": 0
          },
          "deals_created": {
            "type": "integer",
            "title": "Deals Created",
            "default": 0
          },
          "deals_won": {
            "type": "integer",
            "title": "Deals Won",
            "default": 0
          },
          "contact_rate": {
            "type": "number",
            "title": "Contact Rate",
            "default": 0.0
          },
          "qualification_rate": {
            "type": "number",
            "title": "Qualification Rate",
            "default": 0.0
          },
          "deal_rate": {
            "type": "number",
            "title": "Deal Rate",
            "default": 0.0
          },
          "win_rate": {
            "type": "number",
            "title": "Win Rate",
            "default": 0.0
          },
          "overall_conversion": {
            "type": "number",
            "title": "Overall Conversion",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "ConversionFunnel",
        "description": "Lead conversion funnel"
      },
      "DealCreateRequest": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          },
          "amount": {
            "type": "number",
            "minimum": 0.0,
            "title": "Amount"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency",
            "default": "USD"
          },
          "probability": {
            "anyOf": [
              {
                "type": "integer",
                "maximum": 100.0,
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Probability",
            "default": 0
          },
          "expected_close_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Expected Close Date"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "required": [
          "title",
          "amount"
        ],
        "title": "DealCreateRequest",
        "description": "Create deal request"
      },
      "DealResponse": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          },
          "amount": {
            "type": "number",
            "minimum": 0.0,
            "title": "Amount"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency",
            "default": "USD"
          },
          "probability": {
            "anyOf": [
              {
                "type": "integer",
                "maximum": 100.0,
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Probability",
            "default": 0
          },
          "expected_close_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Expected Close Date"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "stage": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Stage"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          },
          "closed_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Closed Date"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "contact_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Name"
          },
          "assigned_to_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To Name"
          },
          "weighted_value": {
            "type": "number",
            "title": "Weighted Value",
            "default": 0.0
          }
        },
        "type": "object",
        "required": [
          "title",
          "amount",
          "id",
          "company_id",
          "created_at",
          "updated_at"
        ],
        "title": "DealResponse",
        "description": "Deal response"
      },
      "DealStats": {
        "properties": {
          "total_deals": {
            "type": "integer",
            "title": "Total Deals",
            "default": 0
          },
          "prospecting": {
            "type": "integer",
            "title": "Prospecting",
            "default": 0
          },
          "negotiation": {
            "type": "integer",
            "title": "Negotiation",
            "default": 0
          },
          "won": {
            "type": "integer",
            "title": "Won",
            "default": 0
          },
          "lost": {
            "type": "integer",
            "title": "Lost",
            "default": 0
          },
          "total_value": {
            "type": "number",
            "title": "Total Value",
            "default": 0.0
          },
          "won_value": {
            "type": "number",
            "title": "Won Value",
            "default": 0.0
          },
          "average_deal_size": {
            "type": "number",
            "title": "Average Deal Size",
            "default": 0.0
          },
          "win_rate": {
            "type": "number",
            "title": "Win Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "DealStats",
        "description": "Deal statistics"
      },
      "DealUpdateRequest": {
        "properties": {
          "title": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "lead_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Lead Id"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "amount": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Amount"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency"
          },
          "probability": {
            "anyOf": [
              {
                "type": "integer",
                "maximum": 100.0,
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Probability"
          },
          "expected_close_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date"
              },
              {
                "type": "null"
              }
            ],
            "title": "Expected Close Date"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "title": "DealUpdateRequest",
        "description": "Update deal request"
      },
      "ForgotPasswordRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          }
        },
        "type": "object",
        "required": [
          "email"
        ],
        "title": "ForgotPasswordRequest"
      },
      "HTTPValidationError": {
        "properties": {
          "detail": {
            "items": {
              "$ref": "#/components/schemas/ValidationError"
            },
            "type": "array",
            "title": "Detail"
          }
        },
        "type": "object",
        "title": "HTTPValidationError"
      },
      "InviteAdminRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name"
        ],
        "title": "InviteAdminRequest",
        "description": "Owner invites a superadmin to a company (gets full admin permissions)"
      },
      "LeadCreateRequest": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "estimated_value": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Estimated Value"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency",
            "default": "USD"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "required": [
          "title"
        ],
        "title": "LeadCreateRequest",
        "description": "Create lead request"
      },
      "LeadResponse": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "estimated_value": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Estimated Value"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency",
            "default": "USD"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "status": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Status"
          },
          "pipeline_stage": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Pipeline Stage"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "contact_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Name"
          },
          "assigned_to_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To Name"
          }
        },
        "type": "object",
        "required": [
          "title",
          "id",
          "company_id",
          "created_at",
          "updated_at"
        ],
        "title": "LeadResponse",
        "description": "Lead response"
      },
      "LeadStats": {
        "properties": {
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "new_leads": {
            "type": "integer",
            "title": "New Leads",
            "default": 0
          },
          "contacted_leads": {
            "type": "integer",
            "title": "Contacted Leads",
            "default": 0
          },
          "qualified_leads": {
            "type": "integer",
            "title": "Qualified Leads",
            "default": 0
          },
          "converted_leads": {
            "type": "integer",
            "title": "Converted Leads",
            "default": 0
          },
          "lost_leads": {
            "type": "integer",
            "title": "Lost Leads",
            "default": 0
          },
          "conversion_rate": {
            "type": "number",
            "title": "Conversion Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "LeadStats",
        "description": "Lead statistics"
      },
      "LeadUpdateRequest": {
        "properties": {
          "title": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Title"
          },
          "contact_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Contact Id"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "source": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100
              },
              {
                "type": "null"
              }
            ],
            "title": "Source"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "estimated_value": {
            "anyOf": [
              {
                "type": "number",
                "minimum": 0.0
              },
              {
                "type": "null"
              }
            ],
            "title": "Estimated Value"
          },
          "currency": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Currency"
          },
          "custom_fields": {
            "anyOf": [
              {
                "additionalProperties": true,
                "type": "object"
              },
              {
                "type": "null"
              }
            ],
            "title": "Custom Fields"
          },
          "tags": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Tags"
          }
        },
        "type": "object",
        "title": "LeadUpdateRequest",
        "description": "Update lead request"
      },
      "LoginRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "password": {
            "type": "string",
            "title": "Password"
          }
        },
        "type": "object",
        "required": [
          "email",
          "password"
        ],
        "title": "LoginRequest"
      },
      "NoteCreateRequest": {
        "properties": {
          "content": {
            "type": "string",
            "minLength": 1,
            "title": "Content"
          },
          "entity_type": {
            "type": "string",
            "maxLength": 50,
            "title": "Entity Type"
          },
          "entity_id": {
            "type": "string",
            "format": "uuid",
            "title": "Entity Id"
          }
        },
        "type": "object",
        "required": [
          "content",
          "entity_type",
          "entity_id"
        ],
        "title": "NoteCreateRequest",
        "description": "Create note request"
      },
      "NoteResponse": {
        "properties": {
          "content": {
            "type": "string",
            "minLength": 1,
            "title": "Content"
          },
          "entity_type": {
            "type": "string",
            "maxLength": 50,
            "title": "Entity Type"
          },
          "entity_id": {
            "type": "string",
            "format": "uuid",
            "title": "Entity Id"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "created_by": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Created By"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "created_by_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Created By Name"
          }
        },
        "type": "object",
        "required": [
          "content",
          "entity_type",
          "entity_id",
          "id",
          "company_id",
          "created_by",
          "created_at",
          "updated_at"
        ],
        "title": "NoteResponse",
        "description": "Note response"
      },
      "NoteUpdateRequest": {
        "properties": {
          "content": {
            "anyOf": [
              {
                "type": "string",
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Content"
          }
        },
        "type": "object",
        "title": "NoteUpdateRequest",
        "description": "Update note request"
      },
      "OperatorAnalytics": {
        "properties": {
          "period": {
            "type": "string",
            "title": "Period",
            "description": "today, week, month, year"
          },
          "date_from": {
            "type": "string",
            "format": "date",
            "title": "Date From"
          },
          "date_to": {
            "type": "string",
            "format": "date",
            "title": "Date To"
          },
          "calls": {
            "$ref": "#/components/schemas/CallStats"
          },
          "leads": {
            "$ref": "#/components/schemas/LeadStats"
          },
          "deals": {
            "$ref": "#/components/schemas/DealStats"
          },
          "tasks": {
            "$ref": "#/components/schemas/TaskStats"
          },
          "total_activities": {
            "type": "integer",
            "title": "Total Activities",
            "default": 0
          },
          "productivity_score": {
            "type": "number",
            "title": "Productivity Score",
            "default": 0.0
          }
        },
        "type": "object",
        "required": [
          "period",
          "date_from",
          "date_to",
          "calls",
          "leads",
          "deals",
          "tasks"
        ],
        "title": "OperatorAnalytics",
        "description": "Operator personal analytics"
      },
      "OperatorDashboard": {
        "properties": {
          "today": {
            "$ref": "#/components/schemas/OperatorAnalytics"
          },
          "this_week": {
            "$ref": "#/components/schemas/OperatorAnalytics"
          },
          "this_month": {
            "$ref": "#/components/schemas/OperatorAnalytics"
          },
          "upcoming_tasks": {
            "type": "integer",
            "title": "Upcoming Tasks",
            "default": 0
          },
          "pending_leads": {
            "type": "integer",
            "title": "Pending Leads",
            "default": 0
          },
          "active_deals": {
            "type": "integer",
            "title": "Active Deals",
            "default": 0
          },
          "recent_calls": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Recent Calls",
            "default": []
          },
          "recent_tasks": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Recent Tasks",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "today",
          "this_week",
          "this_month"
        ],
        "title": "OperatorDashboard",
        "description": "Operator dashboard data"
      },
      "OperatorPerformance": {
        "properties": {
          "user_id": {
            "type": "string",
            "title": "User Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "email": {
            "type": "string",
            "title": "Email"
          },
          "calls": {
            "$ref": "#/components/schemas/CallStats"
          },
          "leads": {
            "$ref": "#/components/schemas/LeadStats"
          },
          "deals": {
            "$ref": "#/components/schemas/DealStats"
          },
          "tasks": {
            "$ref": "#/components/schemas/TaskStats"
          },
          "productivity_score": {
            "type": "number",
            "title": "Productivity Score",
            "default": 0.0
          }
        },
        "type": "object",
        "required": [
          "user_id",
          "name",
          "email",
          "calls",
          "leads",
          "deals",
          "tasks"
        ],
        "title": "OperatorPerformance",
        "description": "Individual operator performance"
      },
      "OwnerDashboard": {
        "properties": {
          "today": {
            "$ref": "#/components/schemas/PlatformAnalytics"
          },
          "this_week": {
            "$ref": "#/components/schemas/PlatformAnalytics"
          },
          "this_month": {
            "$ref": "#/components/schemas/PlatformAnalytics"
          },
          "this_year": {
            "$ref": "#/components/schemas/PlatformAnalytics"
          },
          "system_health": {
            "additionalProperties": true,
            "type": "object",
            "title": "System Health",
            "default": {}
          },
          "growth_trend": {
            "items": {
              "additionalProperties": true,
              "type": "object"
            },
            "type": "array",
            "title": "Growth Trend",
            "default": []
          },
          "churn_analysis": {
            "additionalProperties": true,
            "type": "object",
            "title": "Churn Analysis",
            "default": {}
          }
        },
        "type": "object",
        "required": [
          "today",
          "this_week",
          "this_month",
          "this_year"
        ],
        "title": "OwnerDashboard",
        "description": "Owner platform dashboard"
      },
      "OwnerLoginRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "password": {
            "type": "string",
            "title": "Password"
          }
        },
        "type": "object",
        "required": [
          "email",
          "password"
        ],
        "title": "OwnerLoginRequest",
        "description": "Owner login request schema"
      },
      "OwnerResponse": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "email_verified": {
            "type": "boolean",
            "title": "Email Verified"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name",
          "id",
          "is_active",
          "email_verified",
          "created_at"
        ],
        "title": "OwnerResponse",
        "description": "Owner response"
      },
      "OwnerWithCredentials": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "email_verified": {
            "type": "boolean",
            "title": "Email Verified"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "must_change_password": {
            "type": "boolean",
            "title": "Must Change Password",
            "default": false
          },
          "credentials": {
            "additionalProperties": true,
            "type": "object",
            "title": "Credentials"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name",
          "id",
          "is_active",
          "email_verified",
          "created_at",
          "credentials"
        ],
        "title": "OwnerWithCredentials",
        "description": "Owner response with JWT credentials"
      },
      "PaginatedResponse": {
        "properties": {
          "items": {
            "items": {},
            "type": "array",
            "title": "Items"
          },
          "total": {
            "type": "integer",
            "title": "Total"
          },
          "page": {
            "type": "integer",
            "title": "Page"
          },
          "page_size": {
            "type": "integer",
            "title": "Page Size"
          },
          "total_pages": {
            "type": "integer",
            "title": "Total Pages"
          }
        },
        "type": "object",
        "required": [
          "items",
          "total",
          "page",
          "page_size",
          "total_pages"
        ],
        "title": "PaginatedResponse",
        "description": "Paginated list response"
      },
      "PaymentStatusEnum": {
        "type": "string",
        "enum": [
          "paid",
          "pending",
          "overdue",
          "failed"
        ],
        "title": "PaymentStatusEnum",
        "description": "Payment status enumeration"
      },
      "PermissionGroupCreateRequest": {
        "properties": {
          "name": {
            "type": "string",
            "maxLength": 100,
            "minLength": 1,
            "title": "Name"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "permissions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "minItems": 1,
            "title": "Permissions",
            "description": "List of permission strings"
          }
        },
        "type": "object",
        "required": [
          "name",
          "permissions"
        ],
        "title": "PermissionGroupCreateRequest",
        "description": "Create a custom permission group"
      },
      "PermissionGroupListResponse": {
        "properties": {
          "groups": {
            "items": {
              "$ref": "#/components/schemas/PermissionGroupResponse"
            },
            "type": "array",
            "title": "Groups"
          },
          "total": {
            "type": "integer",
            "title": "Total"
          }
        },
        "type": "object",
        "required": [
          "groups",
          "total"
        ],
        "title": "PermissionGroupListResponse",
        "description": "Permission group list response"
      },
      "PermissionGroupResponse": {
        "properties": {
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Id"
          },
          "name": {
            "type": "string",
            "title": "Name"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "permissions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "title": "Permissions"
          },
          "is_system": {
            "type": "boolean",
            "title": "Is System"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          }
        },
        "type": "object",
        "required": [
          "id",
          "name",
          "permissions",
          "is_system",
          "created_at",
          "updated_at"
        ],
        "title": "PermissionGroupResponse",
        "description": "Permission group response"
      },
      "PermissionGroupUpdateRequest": {
        "properties": {
          "name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 100,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Name"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "permissions": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permissions"
          }
        },
        "type": "object",
        "title": "PermissionGroupUpdateRequest",
        "description": "Update a permission group"
      },
      "PipelineHealth": {
        "properties": {
          "total_value": {
            "type": "number",
            "title": "Total Value",
            "default": 0.0
          },
          "weighted_value": {
            "type": "number",
            "title": "Weighted Value",
            "default": 0.0
          },
          "by_stage": {
            "additionalProperties": true,
            "type": "object",
            "title": "By Stage",
            "default": {}
          },
          "stuck_deals": {
            "type": "integer",
            "title": "Stuck Deals",
            "default": 0
          },
          "forecast": {
            "type": "number",
            "title": "Forecast",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "PipelineHealth",
        "description": "Sales pipeline health"
      },
      "PlatformAnalytics": {
        "properties": {
          "period": {
            "type": "string",
            "title": "Period"
          },
          "date_from": {
            "type": "string",
            "format": "date",
            "title": "Date From"
          },
          "date_to": {
            "type": "string",
            "format": "date",
            "title": "Date To"
          },
          "total_companies": {
            "type": "integer",
            "title": "Total Companies",
            "default": 0
          },
          "active_companies": {
            "type": "integer",
            "title": "Active Companies",
            "default": 0
          },
          "total_users": {
            "type": "integer",
            "title": "Total Users",
            "default": 0
          },
          "active_users": {
            "type": "integer",
            "title": "Active Users",
            "default": 0
          },
          "total_calls": {
            "type": "integer",
            "title": "Total Calls",
            "default": 0
          },
          "total_leads": {
            "type": "integer",
            "title": "Total Leads",
            "default": 0
          },
          "total_deals": {
            "type": "integer",
            "title": "Total Deals",
            "default": 0
          },
          "total_revenue": {
            "type": "number",
            "title": "Total Revenue",
            "default": 0.0
          },
          "new_companies": {
            "type": "integer",
            "title": "New Companies",
            "default": 0
          },
          "new_users": {
            "type": "integer",
            "title": "New Users",
            "default": 0
          },
          "revenue_growth": {
            "type": "number",
            "title": "Revenue Growth",
            "default": 0.0
          },
          "top_companies": {
            "items": {
              "$ref": "#/components/schemas/CompanyPerformance"
            },
            "type": "array",
            "title": "Top Companies",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "period",
          "date_from",
          "date_to"
        ],
        "title": "PlatformAnalytics",
        "description": "Platform-wide analytics (for owners)"
      },
      "ProfileUpdateRequest": {
        "properties": {
          "first_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "language": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 10
              },
              {
                "type": "null"
              }
            ],
            "title": "Language"
          }
        },
        "type": "object",
        "title": "ProfileUpdateRequest",
        "description": "Update own profile (non-admin fields only)"
      },
      "ProviderEnum": {
        "type": "string",
        "enum": [
          "sipuni",
          "binotel"
        ],
        "title": "ProviderEnum",
        "description": "Telephony provider enumeration"
      },
      "RefreshTokenRequest": {
        "properties": {
          "refresh_token": {
            "type": "string",
            "title": "Refresh Token"
          }
        },
        "type": "object",
        "required": [
          "refresh_token"
        ],
        "title": "RefreshTokenRequest",
        "description": "Request body for token refresh"
      },
      "ResetPasswordRequest": {
        "properties": {
          "old_password": {
            "type": "string",
            "minLength": 1,
            "title": "Old Password"
          },
          "new_password": {
            "type": "string",
            "maxLength": 100,
            "minLength": 8,
            "title": "New Password"
          }
        },
        "type": "object",
        "required": [
          "old_password",
          "new_password"
        ],
        "title": "ResetPasswordRequest"
      },
      "SetPasswordRequest": {
        "properties": {
          "token": {
            "type": "string",
            "title": "Token"
          },
          "new_password": {
            "type": "string",
            "maxLength": 100,
            "minLength": 8,
            "title": "New Password"
          }
        },
        "type": "object",
        "required": [
          "token",
          "new_password"
        ],
        "title": "SetPasswordRequest"
      },
      "TaskCreateRequest": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "due_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date-time"
              },
              {
                "type": "null"
              }
            ],
            "title": "Due Date"
          },
          "entity_type": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Type"
          },
          "entity_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Id"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          }
        },
        "type": "object",
        "required": [
          "title"
        ],
        "title": "TaskCreateRequest",
        "description": "Create task request"
      },
      "TaskResponse": {
        "properties": {
          "title": {
            "type": "string",
            "maxLength": 255,
            "minLength": 1,
            "title": "Title"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "due_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date-time"
              },
              {
                "type": "null"
              }
            ],
            "title": "Due Date"
          },
          "entity_type": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Type"
          },
          "entity_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Id"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "type": "string",
            "format": "uuid",
            "title": "Company Id"
          },
          "status": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Status"
          },
          "priority": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Priority"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "created_by": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Created By"
          },
          "completed_at": {
            "anyOf": [
              {
                "type": "string",
                "format": "date-time"
              },
              {
                "type": "null"
              }
            ],
            "title": "Completed At"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "updated_at": {
            "type": "string",
            "format": "date-time",
            "title": "Updated At"
          },
          "assigned_to_name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To Name"
          }
        },
        "type": "object",
        "required": [
          "title",
          "id",
          "company_id",
          "created_at",
          "updated_at"
        ],
        "title": "TaskResponse",
        "description": "Task response"
      },
      "TaskStats": {
        "properties": {
          "total_tasks": {
            "type": "integer",
            "title": "Total Tasks",
            "default": 0
          },
          "pending_tasks": {
            "type": "integer",
            "title": "Pending Tasks",
            "default": 0
          },
          "completed_tasks": {
            "type": "integer",
            "title": "Completed Tasks",
            "default": 0
          },
          "overdue_tasks": {
            "type": "integer",
            "title": "Overdue Tasks",
            "default": 0
          },
          "completion_rate": {
            "type": "number",
            "title": "Completion Rate",
            "default": 0.0
          }
        },
        "type": "object",
        "title": "TaskStats",
        "description": "Task statistics"
      },
      "TaskUpdateRequest": {
        "properties": {
          "title": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 255,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "Title"
          },
          "description": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Description"
          },
          "due_date": {
            "anyOf": [
              {
                "type": "string",
                "format": "date-time"
              },
              {
                "type": "null"
              }
            ],
            "title": "Due Date"
          },
          "assigned_to": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Assigned To"
          },
          "entity_type": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Type"
          },
          "entity_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Entity Id"
          }
        },
        "type": "object",
        "title": "TaskUpdateRequest",
        "description": "Update task request"
      },
      "TeamAnalytics": {
        "properties": {
          "period": {
            "type": "string",
            "title": "Period"
          },
          "date_from": {
            "type": "string",
            "format": "date",
            "title": "Date From"
          },
          "date_to": {
            "type": "string",
            "format": "date",
            "title": "Date To"
          },
          "total_operators": {
            "type": "integer",
            "title": "Total Operators",
            "default": 0
          },
          "active_operators": {
            "type": "integer",
            "title": "Active Operators",
            "default": 0
          },
          "calls": {
            "$ref": "#/components/schemas/CallStats"
          },
          "leads": {
            "$ref": "#/components/schemas/LeadStats"
          },
          "deals": {
            "$ref": "#/components/schemas/DealStats"
          },
          "tasks": {
            "$ref": "#/components/schemas/TaskStats"
          },
          "total_revenue": {
            "type": "number",
            "title": "Total Revenue",
            "default": 0.0
          },
          "revenue_growth": {
            "type": "number",
            "title": "Revenue Growth",
            "default": 0.0
          },
          "top_operators_by_calls": {
            "items": {
              "$ref": "#/components/schemas/OperatorPerformance"
            },
            "type": "array",
            "title": "Top Operators By Calls",
            "default": []
          },
          "top_operators_by_deals": {
            "items": {
              "$ref": "#/components/schemas/OperatorPerformance"
            },
            "type": "array",
            "title": "Top Operators By Deals",
            "default": []
          },
          "top_operators_by_revenue": {
            "items": {
              "$ref": "#/components/schemas/OperatorPerformance"
            },
            "type": "array",
            "title": "Top Operators By Revenue",
            "default": []
          }
        },
        "type": "object",
        "required": [
          "period",
          "date_from",
          "date_to",
          "calls",
          "leads",
          "deals",
          "tasks"
        ],
        "title": "TeamAnalytics",
        "description": "Team-wide analytics (for admins)"
      },
      "UserDetailResponse": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Id"
          },
          "role": {
            "type": "string",
            "title": "Role"
          },
          "permissions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "title": "Permissions"
          },
          "permission_group_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permission Group Id"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "is_suspended": {
            "type": "boolean",
            "title": "Is Suspended"
          },
          "email_verified": {
            "type": "boolean",
            "title": "Email Verified"
          },
          "language": {
            "type": "string",
            "title": "Language"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          },
          "total_calls": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Total Calls",
            "default": 0
          },
          "total_leads": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Total Leads",
            "default": 0
          },
          "total_deals": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Total Deals",
            "default": 0
          },
          "total_tasks": {
            "anyOf": [
              {
                "type": "integer"
              },
              {
                "type": "null"
              }
            ],
            "title": "Total Tasks",
            "default": 0
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name",
          "id",
          "company_id",
          "role",
          "permissions",
          "is_active",
          "is_suspended",
          "email_verified",
          "language",
          "created_at"
        ],
        "title": "UserDetailResponse",
        "description": "Detailed user response with stats"
      },
      "UserInviteRequest": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "role": {
            "type": "string",
            "title": "Role",
            "description": "Role: company_admin or company_operator",
            "default": "company_operator"
          },
          "permissions": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permissions",
            "description": "Custom permissions"
          },
          "permission_group_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permission Group Id",
            "description": "Permission group to assign"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name"
        ],
        "title": "UserInviteRequest",
        "description": "Admin invites operator via email"
      },
      "UserListResponse": {
        "properties": {
          "users": {
            "items": {
              "$ref": "#/components/schemas/UserResponse"
            },
            "type": "array",
            "title": "Users"
          },
          "total": {
            "type": "integer",
            "title": "Total"
          },
          "page": {
            "type": "integer",
            "title": "Page"
          },
          "page_size": {
            "type": "integer",
            "title": "Page Size"
          }
        },
        "type": "object",
        "required": [
          "users",
          "total",
          "page",
          "page_size"
        ],
        "title": "UserListResponse",
        "description": "Paginated user list"
      },
      "UserResponse": {
        "properties": {
          "email": {
            "type": "string",
            "format": "email",
            "title": "Email"
          },
          "first_name": {
            "type": "string",
            "maxLength": 225,
            "minLength": 1,
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "id": {
            "type": "string",
            "format": "uuid",
            "title": "Id"
          },
          "company_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Company Id"
          },
          "role": {
            "type": "string",
            "title": "Role"
          },
          "permissions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "title": "Permissions"
          },
          "permission_group_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permission Group Id"
          },
          "is_active": {
            "type": "boolean",
            "title": "Is Active"
          },
          "is_suspended": {
            "type": "boolean",
            "title": "Is Suspended"
          },
          "email_verified": {
            "type": "boolean",
            "title": "Email Verified"
          },
          "language": {
            "type": "string",
            "title": "Language"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "title": "Created At"
          }
        },
        "type": "object",
        "required": [
          "email",
          "first_name",
          "id",
          "company_id",
          "role",
          "permissions",
          "is_active",
          "is_suspended",
          "email_verified",
          "language",
          "created_at"
        ],
        "title": "UserResponse",
        "description": "User response"
      },
      "UserUpdateRequest": {
        "properties": {
          "first_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225,
                "minLength": 1
              },
              {
                "type": "null"
              }
            ],
            "title": "First Name"
          },
          "last_name": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 225
              },
              {
                "type": "null"
              }
            ],
            "title": "Last Name"
          },
          "phone": {
            "anyOf": [
              {
                "type": "string",
                "maxLength": 50
              },
              {
                "type": "null"
              }
            ],
            "title": "Phone"
          },
          "is_active": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ],
            "title": "Is Active"
          },
          "is_suspended": {
            "anyOf": [
              {
                "type": "boolean"
              },
              {
                "type": "null"
              }
            ],
            "title": "Is Suspended"
          },
          "role": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Role"
          },
          "permissions": {
            "anyOf": [
              {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permissions"
          },
          "permission_group_id": {
            "anyOf": [
              {
                "type": "string",
                "format": "uuid"
              },
              {
                "type": "null"
              }
            ],
            "title": "Permission Group Id",
            "description": "Permission group to assign"
          }
        },
        "type": "object",
        "title": "UserUpdateRequest",
        "description": "Update user information"
      },
      "ValidationError": {
        "properties": {
          "loc": {
            "items": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "integer"
                }
              ]
            },
            "type": "array",
            "title": "Location"
          },
          "msg": {
            "type": "string",
            "title": "Message"
          },
          "type": {
            "type": "string",
            "title": "Error Type"
          }
        },
        "type": "object",
        "required": [
          "loc",
          "msg",
          "type"
        ],
        "title": "ValidationError"
      }
    },
    "securitySchemes": {
      "HTTPBearer": {
        "type": "http",
        "scheme": "bearer"
      }
    }
  }
}
```

</details>

---

## 6. Enums & Dropdown Values

Use these values to populate dropdown selectors, filter chips, and status badges in the UI.

### User Roles

```typescript
enum UserRole {
  OWNER = "owner",              // Platform admin (Owner Panel only)
  COMPANY_ADMIN = "company_admin",   // Full company access
  COMPANY_MANAGER = "company_manager", // Team management
  COMPANY_OPERATOR = "company_operator" // Basic CRM access
}

// For dropdowns when inviting/editing users (Company Panel):
const ASSIGNABLE_ROLES = [
  { value: "company_admin", label: "Admin" },
  { value: "company_manager", label: "Manager" },
  { value: "company_operator", label: "Operator" },
];
```

### Telephony Provider

```typescript
enum ProviderType {
  SIPUNI = "sipuni",
  BINOTEL = "binotel"
}

// Provider config fields (for Company creation form):
const PROVIDER_CONFIG_FIELDS = {
  sipuni: [
    { key: "cabinet_id", label: "Cabinet ID", required: true },
    { key: "security_key", label: "Security Key", required: true },
    { key: "token", label: "Webhook Token", required: false },
  ],
  binotel: [
    { key: "cabinet_id", label: "API Key", required: true },
    { key: "security_key", label: "API Secret", required: true },
    { key: "company_number", label: "Default PBX Number", required: false },
  ],
};
```

### Lead Status

```typescript
enum LeadStatus {
  NEW = "new",
  CONTACTED = "contacted",
  QUALIFIED = "qualified",
  CONVERTED = "converted",
  LOST = "lost"
}

// Colors for status badges:
const LEAD_STATUS_COLORS = {
  new: { bg: "#EFF6FF", text: "#1D4ED8" },       // blue
  contacted: { bg: "#FFF7ED", text: "#C2410C" },  // orange
  qualified: { bg: "#F0FDF4", text: "#15803D" },   // green
  converted: { bg: "#ECFDF5", text: "#047857" },   // emerald
  lost: { bg: "#FEF2F2", text: "#DC2626" },        // red
};
```

### Lead Pipeline Stage

```typescript
enum PipelineStage {
  NEW = "new",
  CONTACT_MADE = "contact_made",
  MEETING_SCHEDULED = "meeting_scheduled",
  PROPOSAL_SENT = "proposal_sent",
  NEGOTIATION = "negotiation",
  WON = "won",
  LOST = "lost"
}

// For Kanban board columns (in order):
const PIPELINE_STAGES = [
  { value: "new", label: "New", color: "#3B82F6" },
  { value: "contact_made", label: "Contact Made", color: "#F59E0B" },
  { value: "meeting_scheduled", label: "Meeting Scheduled", color: "#8B5CF6" },
  { value: "proposal_sent", label: "Proposal Sent", color: "#EC4899" },
  { value: "negotiation", label: "Negotiation", color: "#F97316" },
  { value: "won", label: "Won", color: "#10B981" },
  { value: "lost", label: "Lost", color: "#EF4444" },
];
```

### Deal Stage

```typescript
enum DealStage {
  PROSPECTING = "prospecting",
  QUALIFICATION = "qualification",
  PROPOSAL = "proposal",
  NEGOTIATION = "negotiation",
  CLOSED_WON = "closed_won",
  CLOSED_LOST = "closed_lost"
}

// For deal pipeline Kanban:
const DEAL_STAGES = [
  { value: "prospecting", label: "Prospecting", color: "#3B82F6" },
  { value: "qualification", label: "Qualification", color: "#8B5CF6" },
  { value: "proposal", label: "Proposal", color: "#F59E0B" },
  { value: "negotiation", label: "Negotiation", color: "#F97316" },
  { value: "closed_won", label: "Closed Won", color: "#10B981" },
  { value: "closed_lost", label: "Closed Lost", color: "#EF4444" },
];
```

### Task Status & Priority

```typescript
enum TaskStatus {
  PENDING = "pending",
  IN_PROGRESS = "in_progress",
  COMPLETED = "completed",
  CANCELLED = "cancelled"
}

enum TaskPriority {
  LOW = "low",
  MEDIUM = "medium",
  HIGH = "high",
  URGENT = "urgent"
}

const TASK_STATUS_OPTIONS = [
  { value: "pending", label: "Pending", icon: "clock", color: "#6B7280" },
  { value: "in_progress", label: "In Progress", icon: "play", color: "#3B82F6" },
  { value: "completed", label: "Completed", icon: "check", color: "#10B981" },
  { value: "cancelled", label: "Cancelled", icon: "x", color: "#EF4444" },
];

const TASK_PRIORITY_OPTIONS = [
  { value: "low", label: "Low", color: "#6B7280" },
  { value: "medium", label: "Medium", color: "#F59E0B" },
  { value: "high", label: "High", color: "#F97316" },
  { value: "urgent", label: "Urgent", color: "#EF4444" },
];
```

### Call Enums

```typescript
enum CallStatus {
  ANSWER = "ANSWER",
  BUSY = "BUSY",
  NOANSWER = "NOANSWER",
  CANCEL = "CANCEL",
  CONGESTION = "CONGESTION",
  CHANUNAVAIL = "CHANUNAVAIL"
}

enum CallDirection {
  INBOUND = "inbound",
  OUTBOUND = "outbound",
  INTERNAL = "internal"
}

enum CallOutcome {
  // Positive
  INTERESTED = "interested",
  APPOINTMENT_SCHEDULED = "appointment_scheduled",
  FOLLOW_UP = "follow_up",
  SALE_MADE = "sale_made",
  // Neutral
  NO_ANSWER = "no_answer",
  LEFT_VOICEMAIL = "left_voicemail",
  BUSY = "busy",
  CALLBACK_REQUESTED = "callback_requested",
  INFORMATION_PROVIDED = "information_provided",
  // Negative
  NOT_INTERESTED = "not_interested",
  WRONG_NUMBER = "wrong_number",
  DO_NOT_CALL = "do_not_call",
  CUSTOMER_COMPLAINT = "customer_complaint",
  // Other
  OTHER = "other"
}

// Group outcomes for dropdown with sections:
const CALL_OUTCOME_GROUPS = {
  "Positive": ["interested", "appointment_scheduled", "follow_up", "sale_made"],
  "Neutral": ["no_answer", "left_voicemail", "busy", "callback_requested", "information_provided"],
  "Negative": ["not_interested", "wrong_number", "do_not_call", "customer_complaint"],
  "Other": ["other"],
};
```

### Contract & Billing Enums

```typescript
enum ContractStatus {
  ACTIVE = "active",
  WARNING = "warning",
  GRACE_PERIOD = "grace_period",
  EXPIRED = "expired",
  SUSPENDED = "suspended",
  CANCELLED = "cancelled"
}

enum BillingPeriod {
  MONTHLY = "monthly",
  YEARLY = "yearly"
}

enum PaymentStatus {
  PAID = "paid",
  PENDING = "pending",
  OVERDUE = "overdue",
  FAILED = "failed"
}

const CONTRACT_STATUS_COLORS = {
  active: { bg: "#ECFDF5", text: "#047857" },
  warning: { bg: "#FFF7ED", text: "#C2410C" },
  grace_period: { bg: "#FEF3C7", text: "#92400E" },
  expired: { bg: "#FEF2F2", text: "#DC2626" },
  suspended: { bg: "#F3F4F6", text: "#374151" },
  cancelled: { bg: "#FEF2F2", text: "#991B1B" },
};
```

### Note/Task Entity Types

```typescript
// Polymorphic entity linking — notes and tasks can be attached to:
const ENTITY_TYPES = [
  { value: "lead", label: "Lead" },
  { value: "contact", label: "Contact" },
  { value: "deal", label: "Deal" },
  { value: "call", label: "Call" },   // Notes only
];
```

---

## 7. Data Schemas Reference

### Contact

```typescript
interface Contact {
  id: string;           // UUID
  company_id: string;   // UUID
  first_name: string;   // required, 1-255 chars
  last_name?: string;   // 0-255 chars
  email?: string;       // valid email
  phone?: string;       // 0-50 chars
  company_name?: string;
  position?: string;
  source?: string;      // e.g. "website", "referral", "cold_call"
  tags?: string[];      // ["vip", "enterprise"]
  custom_fields?: Record<string, any>;  // arbitrary key-value
  created_by?: string;  // UUID of creator
  assigned_to?: string; // UUID of assignee (for assignment dropdown)
  total_leads: number;
  total_deals: number;
  total_calls: number;
  created_at: string;   // ISO 8601
  updated_at: string;
}
```

### Lead

```typescript
interface Lead {
  id: string;
  company_id: string;
  title: string;            // required, 1-255 chars
  contact_id?: string;      // UUID — link to Contact (searchable dropdown)
  source?: string;
  description?: string;
  estimated_value?: number; // >= 0
  currency?: string;        // default "USD"
  status?: LeadStatus;      // dropdown
  pipeline_stage?: PipelineStage;  // Kanban column
  assigned_to?: string;     // UUID — user assignment dropdown
  tags?: string[];
  custom_fields?: Record<string, any>;
  contact_name?: string;    // computed
  assigned_to_name?: string;
  created_at: string;
  updated_at: string;
}
```

### Deal

```typescript
interface Deal {
  id: string;
  company_id: string;
  title: string;
  contact_id?: string;      // searchable contact dropdown
  lead_id?: string;         // searchable lead dropdown
  amount: number;           // required, >= 0
  currency?: string;
  stage?: DealStage;        // Kanban column / dropdown
  probability?: number;     // 0-100, slider
  expected_close_date?: string; // date picker
  closed_date?: string;
  description?: string;
  assigned_to?: string;
  tags?: string[];
  custom_fields?: Record<string, any>;
  contact_name?: string;
  assigned_to_name?: string;
  weighted_value: number;   // amount * probability / 100
  created_at: string;
  updated_at: string;
}
```

### Task

```typescript
interface Task {
  id: string;
  company_id: string;
  title: string;
  description?: string;
  status?: TaskStatus;       // dropdown
  priority?: TaskPriority;   // dropdown with colors
  due_date?: string;         // datetime picker
  completed_at?: string;
  assigned_to?: string;      // user dropdown
  created_by?: string;
  entity_type?: string;      // "lead" | "contact" | "deal"
  entity_id?: string;        // UUID of linked entity
  assigned_to_name?: string;
  created_at: string;
  updated_at: string;
}
```

### Note

```typescript
interface Note {
  id: string;
  company_id: string;
  content: string;           // required, rich text
  entity_type: string;       // required: "lead" | "contact" | "deal" | "call"
  entity_id: string;         // required: UUID of linked entity
  created_by?: string;
  created_by_name?: string;
  created_at: string;
  updated_at: string;
}
```

### Call Event

```typescript
interface CallEvent {
  id: string;
  company_id: string;
  provider_type: "sipuni" | "binotel";
  provider_call_id: string;
  phone_1: string;           // external number
  phone_2: string;           // internal number
  operator_id?: string;
  direction: CallDirection;
  state: CallStatus;
  attempts: number;
  waiting_sec?: number;
  billing_sec?: number;
  record_url?: string;       // call recording URL
  call_start_timestamp: number;  // Unix timestamp
  call_end_timestamp?: number;
  contact_id?: string;
  lead_id?: string;
  deal_id?: string;
  outcome?: CallOutcome;     // dropdown with grouped options
  disposition_notes?: string;
  created_at: string;
  updated_at: string;
}
```

### User

```typescript
interface User {
  id: string;
  company_id?: string;
  email: string;
  first_name: string;
  last_name?: string;
  phone?: string;
  role: UserRole;             // dropdown (admin, manager, operator)
  permissions: string[];      // multi-select from permissions list
  permission_group_id?: string; // dropdown from permission groups
  is_active: boolean;         // toggle
  is_suspended: boolean;      // toggle
  email_verified: boolean;
  language: string;           // dropdown: "en", "ru", "uz"
  created_at: string;
}
```

### Permission Group

```typescript
interface PermissionGroup {
  id: string;
  company_id?: string;       // null = system group (read-only)
  name: string;
  description?: string;
  permissions: string[];      // multi-select from available permissions
  is_system: boolean;         // if true, cannot edit/delete
  created_at: string;
  updated_at: string;
}
```

### Company (Owner Panel)

```typescript
interface Company {
  id: string;
  name: string;
  subdomain: string;
  provider_type: "sipuni" | "binotel";  // dropdown
  provider_config: SipuniConfig | BinotelConfig;
  is_active: boolean;
  webhook_url?: string;      // read-only, generated by backend
  webhook_token: string;     // read-only
  settings?: {
    timezone?: string;       // dropdown (e.g. "Asia/Tashkent")
    language?: string;       // dropdown
  };
  created_at: string;
  updated_at: string;
}

interface SipuniConfig {
  cabinet_id: string;
  security_key: string;
  token?: string;
}

interface BinotelConfig {
  cabinet_id: string;        // API Key
  security_key: string;      // API Secret
  company_number?: string;
}
```

### Contract (Owner Panel)

```typescript
interface Contract {
  id: string;
  owner_id: string;
  company_id: string;
  name: string;
  max_admins: number;        // >= 1
  max_managers: number;      // >= 0
  max_operators: number;     // >= 0
  max_storage_gb: number;    // >= 1
  price: number;             // >= 0, decimal
  currency: string;          // 3-letter code
  billing_period: BillingPeriod;  // dropdown
  status: ContractStatus;    // dropdown
  payment_status: PaymentStatus;
  start_date: string;        // date picker
  end_date: string;
  next_payment_date?: string;
  grace_period_days: number; // default 30
  is_active: boolean;
  auto_renew: boolean;       // toggle
  notes?: string;
  company_name?: string;     // computed
  days_until_expiry?: number;
  // Detail fields (from GET /contracts/{id}):
  current_admins?: number;
  current_managers?: number;
  current_operators?: number;
  created_at: string;
  updated_at: string;
}
```

---

## 8. Permission System

### Available Permissions

Fetch dynamically from `GET /api/v1/company/permission-groups/permissions`:

```json
{
  "permissions": [
    "calls.make", "calls.read", "calls.write",
    "company.delete", "company.manage", "company.read",
    "contacts.delete", "contacts.export", "contacts.import", "contacts.read", "contacts.write",
    "contract.read",
    "deals.assign", "deals.delete", "deals.read", "deals.write",
    "leads.assign", "leads.delete", "leads.read", "leads.write",
    "notes.delete", "notes.read", "notes.write",
    "settings.manage", "settings.read",
    "stats.export", "stats.read",
    "tasks.assign", "tasks.delete", "tasks.read", "tasks.write",
    "users.create", "users.delete", "users.manage", "users.read", "users.update", "users.write"
  ],
  "grouped": {
    "calls": ["calls.make", "calls.read", "calls.write"],
    "company": ["company.delete", "company.manage", "company.read"],
    "contacts": ["contacts.delete", "contacts.export", "contacts.import", "contacts.read", "contacts.write"],
    "contract": ["contract.read"],
    "deals": ["deals.assign", "deals.delete", "deals.read", "deals.write"],
    "leads": ["leads.assign", "leads.delete", "leads.read", "leads.write"],
    "notes": ["notes.delete", "notes.read", "notes.write"],
    "settings": ["settings.manage", "settings.read"],
    "stats": ["stats.export", "stats.read"],
    "tasks": ["tasks.assign", "tasks.delete", "tasks.read", "tasks.write"],
    "users": ["users.create", "users.delete", "users.manage", "users.read", "users.update", "users.write"]
  }
}
```

### Role → Default Permissions

| Permission | Admin | Manager | Operator |
|-----------|-------|---------|----------|
| leads.read | Y | Y | Y |
| leads.write | Y | Y | - |
| leads.delete | Y | - | - |
| leads.assign | Y | Y | - |
| contacts.read | Y | Y | Y |
| contacts.write | Y | Y | - |
| contacts.delete | Y | - | - |
| contacts.import | Y | Y | - |
| contacts.export | Y | Y | - |
| deals.read | Y | Y | Y |
| deals.write | Y | Y | - |
| deals.delete | Y | - | - |
| deals.assign | Y | Y | - |
| tasks.read | Y | Y | Y |
| tasks.write | Y | Y | Y |
| tasks.delete | Y | - | - |
| tasks.assign | Y | Y | - |
| calls.read | Y | Y | Y |
| calls.write | Y | Y | Y |
| calls.make | Y | Y | Y |
| notes.read | Y | Y | Y |
| notes.write | Y | Y | Y |
| notes.delete | Y | - | - |
| users.read | Y | Y | - |
| users.create | Y | - | - |
| users.update | Y | - | - |
| users.write | Y | - | - |
| users.delete | Y | - | - |
| users.manage | Y | - | - |
| stats.read | Y | Y | - |
| stats.export | Y | - | - |
| settings.read | Y | Y | - |
| settings.manage | Y | - | - |
| company.read | Y | Y | Y |
| company.manage | Y | - | - |
| company.delete | - | - | - |
| contract.read | Y | - | - |

### Effective Permissions

A user's effective permissions are: `individual permissions ∪ permission group permissions`

Both individual permissions and permission group membership can be set when inviting/editing a user.

### Frontend Permission UI

For the **User Invite/Edit form**, render permissions as grouped checkboxes:

```
Permissions:
  ┌─ Leads ────────────────────────┐
  │ [x] leads.read                 │
  │ [x] leads.write                │
  │ [ ] leads.delete               │
  │ [x] leads.assign               │
  └────────────────────────────────┘
  ┌─ Contacts ─────────────────────┐
  │ [x] contacts.read              │
  │ ...                            │
  └────────────────────────────────┘
```

For **Permission Groups**, provide a similar grouped checkbox UI plus a name/description field.

When editing a user, also provide a **Permission Group dropdown** that auto-applies group permissions.

---

## 9. Frontend Implementation Requirements

> **These requirements command both sides of the project — the Owner Panel and the Company Panel. Each is a separate React app.**

### Tech Stack (Both Apps)

- React 18+ with TypeScript
- React Router v6 for routing
- Axios for API calls with interceptors (JWT auto-attach, token refresh, error handling)
- shadcn/ui component library (built on Radix UI + Tailwind CSS)
- Tailwind CSS for styling
- React Hook Form + Zod for form validation
- TanStack Query (React Query) for server state management and caching
- Recharts or Tremor for dashboard charts
- date-fns for date formatting
- Lucide React for icons

---

## 10. Company Panel — Full Requirements

**Subdomain:** `<company>.localhost:3000`
**API Base:** `/api/v1/auth/*` + `/api/v1/company/*`
**Users:** company_admin, company_manager, company_operator

### 10.1 Authentication Pages

#### Login Page (`/login`)

- Email + password form
- Sends `POST /api/v1/auth/login` with `Origin` header set to the current subdomain
- On success: if `must_change_password: true`, redirect to `/set-password` with `temporary_token` in state; otherwise store `access` and `refresh` tokens in localStorage and redirect to `/`
- "Forgot password?" link → `/forgot-password`
- Password validation: min 8 chars, at least 1 uppercase, at least 1 digit
- Show inline error on 401/403

#### Set Password Page (`/set-password`)

- "New password" + "Confirm password" fields
- Sends `POST /api/v1/auth/set-password` with `{ token, new_password }`
- On success: store returned credentials, redirect to `/`
- Handles both first-login and forgot-password flows (token comes from login response or URL query param)

#### Forgot Password Page (`/forgot-password`)

- Email input field
- Sends `POST /api/v1/auth/forgot-password` with `Origin` header
- Always shows success message (API prevents email enumeration)
- Link back to `/login`

#### Change Password (inside `/profile`)

- Old password + new password + confirm fields
- Sends `POST /api/v1/auth/reset-password` with `{ old_password, new_password }`
- Requires active JWT (`Authorization: Bearer`)

#### Token Refresh

- Axios interceptor: on 401 response, attempt `POST /api/v1/auth/refresh` with `{ refresh_token }`
- If refresh succeeds, retry original request with new access token
- If refresh fails, clear tokens and redirect to `/login`

### 10.2 Layout & Navigation

#### Sidebar Navigation

Collapsible sidebar with the following items (visibility controlled by permissions from JWT):

| Menu Item | Route | Icon | Required Permission |
|-----------|-------|------|-------------------|
| Dashboard | `/` | LayoutDashboard | — (all users) |
| Contacts | `/contacts` | Users | `contacts.read` |
| Leads | `/leads` | Target | `leads.read` |
| Deals | `/deals` | Handshake | `deals.read` |
| Tasks | `/tasks` | CheckSquare | `tasks.read` |
| Calls | `/calls` | Phone | `calls.read` |
| Notes | `/notes` | FileText | `notes.read` |
| **Settings** (section) | | | |
| ├ Users | `/settings/users` | UserCog | `users.read` |
| ├ Permissions | `/settings/permission-groups` | Shield | `settings.read` |
| └ Contract | `/settings/contract` | ScrollText | `contract.read` |

**Header bar:** Current user avatar/name, role badge, profile dropdown (Profile, Change Password, Logout).

**Responsive:** Sidebar collapses to hamburger on mobile. Content is full-width on mobile.

### 10.3 Dashboard Page (`/`)

**Two views based on role:**

#### Operator Dashboard (company_operator)

API: `GET /api/v1/company/analytics/me/dashboard`

- **Quick stats cards (top row):** Today's Calls, Pending Leads, Active Deals, Upcoming Tasks — each with count and trend indicator
- **Today's performance panel:** Calls made/answered/missed, success rate progress bar
- **Recent calls list:** Last 5 calls with phone number, direction badge (inbound/outbound), duration, timestamp
- **My tasks today:** List from `GET /api/v1/company/tasks/my-today` — title, priority badge (color-coded: urgent=red, high=orange, medium=yellow, low=gray), due date, overdue indicator
- **Period selector:** Today / This Week / This Month tabs switching analytics view

#### Admin Dashboard (company_admin, company_manager)

API: `GET /api/v1/company/analytics/team/dashboard`

- **Summary stats cards:** Total Operators (active/total), Total Calls, Total Revenue, Win Rate — with period comparison
- **Conversion funnel chart:** Leads → Contacted → Qualified → Deals Created → Deals Won (horizontal funnel or vertical bar)
- **Pipeline health card:** Total pipeline value, weighted value, stuck deals count, forecast
- **Calls trend chart:** Line chart of last 7 days call volume
- **Revenue trend chart:** Line/bar chart of last 30 days revenue
- **Peak call hours heatmap:** Hourly distribution for the week
- **Top operators leaderboard:** Table of top 5 by calls and by revenue with name, email, call count, deal value
- **Period selector:** Today / Week / Month / Year

### 10.4 Contacts Page (`/contacts`)

API: `GET /api/v1/company/contacts`

#### List View

- **Card layout** with contact cards showing: full name, company, phone, email, source badge
- Each card has **related counts badges**: Leads (count), Deals (count), Calls (count)
- **Search bar:** Real-time search by name, phone, email, company (uses `?search=` param)
- **Filter sidebar/dropdowns:**
  - `assigned_to` — user dropdown
  - `has_email` — yes/no toggle
  - `has_phone` — yes/no toggle
  - `created_by` — user dropdown
- **Pagination:** Page selector, items per page (10/20/50/100)
- **Create button:** Opens create/edit form (requires `contacts.write`)
- **Bulk create button:** Upload CSV or multi-entry form (max 100, requires `contacts.write`)

#### Contact Detail Page (`/contacts/:id`)

API: `GET /api/v1/company/contacts/{id}` + `GET /api/v1/company/contacts/{id}/activity`

- **Contact info card:** All fields (first_name, last_name, email, phone, company_name, position, source, custom_fields as key-value table, tags as colored chips)
- **Edit button** (requires `contacts.write`) → opens inline edit form
- **Delete button** (requires `contacts.delete`) → confirmation dialog, soft delete by default
- **Activity timeline tabs:**
  - **Leads tab:** List of linked leads with title, status badge, date
  - **Deals tab:** List of linked deals with title, stage badge, amount
  - **Calls tab:** List of calls with direction, duration, date
  - **Notes tab:** Notes timeline with content, author, date — inline add note form (requires `notes.write`)

#### Create/Edit Contact Form

Fields:
- first_name* (text, min 1, max 255)
- last_name (text, max 255)
- email (email validation)
- phone (text, max 50)
- company_name (text, max 255)
- position (text, max 255)
- source (text, max 100)
- tags (multi-select/tag input)
- custom_fields (dynamic key-value pairs — add/remove rows)

### 10.5 Leads Page (`/leads`)

API: `GET /api/v1/company/leads`

#### Table View (default)

- Columns: Title, Contact Name, Status, Pipeline Stage, Assigned To, Estimated Value, Source, Created
- **Status badges:** color-coded — new (blue), contacted (yellow), qualified (green), converted (purple), lost (red)
- **Pipeline stage badges:** new → contact_made → meeting_scheduled → proposal_sent → negotiation → won → lost
- Sortable columns, row click → detail page

#### Kanban View (toggle)

- Columns = Pipeline Stages (new, contact_made, meeting_scheduled, proposal_sent, negotiation, won, lost)
- Each card shows: title, contact name, estimated value, assigned user avatar
- Drag & drop between columns → `PUT /api/v1/company/leads/{id}` to update pipeline_stage

#### Filters

- `search` — text search
- `status_filter` — dropdown (new, contacted, qualified, converted, lost)
- `assigned_to` — searchable user dropdown
- `source` — text
- `min_value` / `max_value` — number range
- `my_leads` — toggle (shows only user's leads)

#### Lead Actions

- **Create** (requires `leads.write`): form with title*, contact_id (searchable contact dropdown), source, description, estimated_value, currency, assigned_to (user dropdown), tags
- **Edit** (requires `leads.write`): same fields, partial update
- **Delete** (requires `leads.delete`): confirmation dialog
- **Convert to Deal** (requires `leads.write` + `deals.write`): `POST /api/v1/company/leads/{id}/convert` — checkbox "Create deal from lead", shows success with deal link
- **Assign** (requires `leads.assign`): `POST /api/v1/company/leads/{id}/assign` — user dropdown

### 10.6 Deals Page (`/deals`)

API: `GET /api/v1/company/deals`

#### Pipeline Kanban View (default)

- Columns = Deal Stages: prospecting, qualification, proposal, negotiation, closed_won, closed_lost
- Each card: title, contact name, amount (formatted currency), probability %, weighted value, assigned user
- Column headers show: stage name, deal count, total value for that stage
- Drag & drop between stages → `PUT /api/v1/company/deals/{id}` with new stage
- Won/lost columns have distinct visual treatment (green/red backgrounds)

#### Table View (toggle)

- Columns: Title, Contact, Stage, Amount, Probability, Weighted Value, Expected Close, Assigned To
- Sortable columns

#### Pipeline Summary

API: `GET /api/v1/company/deals/pipeline/summary`
- Show as a pipeline summary bar/card above the board: total deals, total value, weighted value per stage

#### Filters

- `search` — text search
- `stage` — dropdown (all deal stages)
- `assigned_to` — user dropdown
- `min_value` / `max_value` — amount range
- `my_deals` — toggle

#### Deal Actions

- **Create** (requires `deals.write`): title*, contact_id (searchable), lead_id (searchable), amount*, currency, probability (0-100 slider), expected_close_date (date picker), description, assigned_to, tags
- **Edit** (requires `deals.write`): same fields, partial update
- **Delete** (requires `deals.delete`): confirmation dialog
- **Mark Won** (requires `deals.write`): `POST /api/v1/company/deals/{id}/win` — optional win reason, triggers confetti animation
- **Mark Lost** (requires `deals.write`): `POST /api/v1/company/deals/{id}/lose` — optional loss reason

### 10.7 Tasks Page (`/tasks`)

API: `GET /api/v1/company/tasks`

#### List View

- Cards or table with: title, status badge, priority badge (color-coded), assigned user, due date, entity link (if linked to lead/contact/deal)
- **Overdue indicator:** Red border/highlight for tasks past due date that aren't completed
- Tasks sorted by due date (ascending, nulls last), then by priority (descending)

#### Filters

- `search` — text
- `status_filter` — dropdown (pending, in_progress, completed, cancelled)
- `priority` — dropdown (low, medium, high, urgent)
- `assigned_to` — user dropdown
- `overdue` — toggle
- `my_tasks` — toggle

#### My Tasks Today Widget

API: `GET /api/v1/company/tasks/my-today`
- Sidebar or top widget showing today's pending tasks with priority badges and overdue flags

#### Task Actions

- **Create** (requires `tasks.write`): title*, description, due_date (datetime picker), assigned_to (user dropdown, defaults to self), entity_type (contact/lead/deal dropdown), entity_id (searchable based on entity_type)
- **Edit** (requires `tasks.write`): operators can only edit own tasks
- **Delete** (requires `tasks.delete`): admin only
- **Complete** (requires `tasks.write`): `POST /api/v1/company/tasks/{id}/complete` — checkmark button, operators can only complete own tasks
- Status transitions via edit: pending → in_progress → completed / cancelled

### 10.8 Calls Page (`/calls`)

API: `GET /api/v1/company/calls`

#### Call Log Table

- Columns: Direction (badge), Phone 1, Phone 2, Operator, Status (badge), Duration, Waiting Time, Date
- **Direction badges:** inbound (green arrow down), outbound (blue arrow up), internal (gray arrows)
- **Status badges:** ANSWER (green), BUSY (orange), NOANSWER (red), CANCEL (gray), CONGESTION (red), CHANUNAVAIL (red)
- Duration formatted as mm:ss
- Recording icon button (if `record_url` present) → plays audio or downloads

#### Call Actions

- **Make Call** (requires `calls.make`): `POST /api/v1/company/calls` — form with phone_1*, phone_2*, operator_id (optional), shows result with call_id or error
- **View Recording** (requires `calls.read`): `GET /api/v1/company/calls/{id}/recording` — returns signed URL, embed audio player

#### Call Detail View (`/calls/:id`)

- Full call details: provider, phones, operator, direction, status, timestamps, duration, waiting time
- Audio player for recording (if available)
- Linked contact (if contact_id present)
- Linked lead (if lead_id present)
- Notes tab: show/add notes for this call entity

### 10.9 Notes

Notes are **not a standalone page** — they appear as timeline sections on entity detail pages (contacts, leads, deals, tasks, calls).

#### Notes Timeline Component

API: `GET /api/v1/company/notes/timeline/{entity_type}/{entity_id}`

- Chronological list of notes: content (markdown-rendered or plain text), author name, creation date
- **Add note form** (requires `notes.write`): textarea + submit button
- **Edit button** on own notes (requires `notes.write`)
- **Delete button** on own notes (requires `notes.delete`), admins can delete any

#### Standalone Notes List (`/notes` — optional)

API: `GET /api/v1/company/notes`
- Filter by entity type, entity ID, creator
- Search by content

### 10.10 Settings — User Management (`/settings/users`)

**Requires:** `users.read` permission (typically admin only)

#### User List

API: `GET /api/v1/company/users`

- Table: Name, Email, Role (badge), Status (active/suspended/inactive badges), Permission Group, Created
- Search by name/email
- Filter by role (`company_admin`, `company_manager`, `company_operator`), active status
- Pagination

#### User Detail (`/settings/users/:id`)

API: `GET /api/v1/company/users/{id}`

- User info card with stats: total calls, leads, deals, tasks
- Edit form (requires `users.update`): name, phone, role dropdown, permissions (checkbox grid or permission group dropdown), active toggle, suspended toggle
- Permission group dropdown (searchable, from `GET /api/v1/company/permission-groups`)
- **Activate / Deactivate buttons** (requires `users.update`): `POST .../activate` or `POST .../deactivate`
- **Delete button** (requires `users.delete`): confirmation, cannot delete self

#### Invite User Form

API: `POST /api/v1/company/users/invite`
**Requires:** `users.create`

- Fields: email*, first_name*, last_name, phone, role (dropdown: company_admin, company_manager, company_operator), permission_group_id (searchable dropdown), custom permissions (checkbox grid — optional override)
- Shows contract user limits and current counts (from `GET /api/v1/company/contract`)
- On success: shows message "Invitation sent to email"
- On 409: "User with this email already exists"

### 10.11 Settings — Permission Groups (`/settings/permission-groups`)

**Requires:** `settings.read` to view, `settings.manage` to create/edit/delete

#### Available Permissions Reference

API: `GET /api/v1/company/permission-groups/permissions`
- Show all permissions grouped by resource (leads, contacts, deals, tasks, calls, notes, users, stats, settings, company, contract)

#### Permission Group List

API: `GET /api/v1/company/permission-groups`

- Table: Name, Description, Permission Count, System (badge), Actions
- System groups shown as read-only with "System" badge
- Custom groups have edit/delete buttons

#### Create/Edit Permission Group Form

- name* (text, max 100)
- description (text)
- permissions* (checkbox grid grouped by resource — check/uncheck individual permissions)
  - Group headers with "select all" toggle per resource
  - Visual: grid layout with resource rows and action columns (read, write, delete, assign, etc.)
- System groups cannot be edited or deleted

### 10.12 Settings — Contract (`/settings/contract`)

**Requires:** `contract.read`

API: `GET /api/v1/company/contract`

- **Contract info card:** name, status badge (color-coded: active=green, warning=yellow, grace_period=orange, expired=red, suspended=red, cancelled=gray), payment status badge (paid=green, pending=yellow, overdue=red, failed=red)
- **Usage meters:** progress bars showing current/max for admins, managers, operators, storage
- **Dates:** start date, end date, days until expiry, billing period, auto-renew toggle (read-only)
- **Warnings list:** rendered as alert banners (yellow/red) if any warnings exist

### 10.13 Profile Page (`/profile`)

#### View/Edit Profile

API: `GET /api/v1/company/users/me` + `PUT /api/v1/company/users/me`

- Fields: first_name, last_name, phone, language
- Shows role, email (read-only), permissions list (read-only)

#### Change Password Section

API: `POST /api/v1/auth/reset-password`

- Old password, new password, confirm password
- Password strength indicator
- Validation: min 8, 1 uppercase, 1 digit

---

## 11. Owner Panel — Full Requirements

**Subdomain:** `owners.localhost:3000`
**API Base:** `/api/v1/owner/*`
**Users:** Owner (platform admin) only

### 11.1 Authentication Pages

#### Login Page (`/login`)

- Email + password form
- Sends `POST /api/v1/owner/auth/login` (no Origin header needed)
- Same password change flow as company (check `must_change_password`)
- On success: store tokens, redirect to `/`

#### Set Password / Forgot Password

- Same pattern as company panel but uses `/api/v1/owner/auth/set-password` and `/api/v1/owner/auth/forgot-password`

### 11.2 Layout & Navigation

#### Sidebar Navigation

| Menu Item | Route | Icon |
|-----------|-------|------|
| Dashboard | `/` | LayoutDashboard |
| Companies | `/companies` | Building2 |
| Contracts | `/contracts` | ScrollText |
| Permissions | `/permissions` | Shield |
| Profile | `/profile` | User |

**Header bar:** Owner name, profile dropdown (Profile, Change Password, Logout)

### 11.3 Dashboard Page (`/`)

API: `GET /api/v1/owner/analytics/dashboard`

- **Platform stats cards (top row):** Total Companies (active/total), Total Users (active/total), Total Calls, Total Revenue — each for today/week/month/year with period tabs
- **Growth trend chart:** Line chart of last 30 days showing companies, users, daily revenue
- **Top companies table:** Ranked by revenue — company name, users count (active), total deals, total revenue, growth rate
- **System health card:** Status indicator, uptime, average response time
- **Churn analysis card:** Churned companies count, churn rate
- **Period selector:** Today / Week / Month / Year tabs
- **Clear cache button:** `DELETE /api/v1/owner/analytics/cache`

### 11.4 Companies Page (`/companies`)

API: `GET /api/v1/owner/companies`

#### Company List

- **Card layout:** Each card shows: company name, subdomain, provider type badge (sipuni=blue, binotel=green), active status badge, users count, webhook URL (copyable), created date
- **Create Company button** → `/companies/new`

#### Company Detail Page (`/companies/:id`)

API: `GET /api/v1/owner/companies/{id}`

- **Company info card:** name, subdomain, provider type (read-only after creation), active status toggle, webhook URL (copy button), webhook token (masked, reveal on click)
- **Provider config card:** Shows Sipuni config (cabinet_id, security_key, token) or Binotel config (cabinet_id, security_key, company_number) — sensitive fields masked with reveal toggle
- **Settings card:** JSON settings viewer/editor
- **Users count**
- **Edit form:** `PUT /api/v1/owner/companies/{id}` — name, settings, is_active
- **Action buttons:**
  - Activate: `POST /api/v1/owner/companies/{id}/activate`
  - Deactivate: `POST /api/v1/owner/companies/{id}/deactivate`
  - Delete: `DELETE /api/v1/owner/companies/{id}` — confirmation dialog, hard delete option
- **Invite Admin button:** Opens invite form → `POST /api/v1/owner/companies/{id}/invite-admin`
  - Fields: email*, first_name*, last_name, phone
  - Creates a company_admin user with full permissions, sends email invitation

#### Create Company Wizard (`/companies/new`)

API: `POST /api/v1/owner/companies`

Multi-step form:
1. **Company Info:** name*, subdomain (optional, auto-generated from name)
2. **Provider Selection:** radio buttons — Sipuni or Binotel. **Conditional fields:**
   - **Sipuni:** cabinet_id*, security_key*, token (optional)
   - **Binotel:** cabinet_id*, security_key*, company_number (optional)
3. **Settings:** timezone dropdown, language dropdown (optional JSON)
4. **Review & Create:** Summary of all fields, confirm button

After creation: show success with webhook URL (copy to clipboard), redirect to company detail page

### 11.5 Contracts Page (`/contracts`)

API: `GET /api/v1/owner/contracts`

#### Contract List

- Table: Company Name, Contract Name, Status (badge), Payment Status (badge), Price, Billing Period, Start Date, End Date, Days Until Expiry, Auto-Renew
- **Status badges:** active=green, warning=yellow, grace_period=orange, expired=red, suspended=red, cancelled=gray
- **Payment badges:** paid=green, pending=yellow, overdue=red, failed=red
- **Filters:** company_id (dropdown from companies list), status (dropdown)
- **Create button** → form

#### Contract Detail Page (`/contracts/:id`)

API: `GET /api/v1/owner/contracts/{id}`

- **Contract info card:** all fields including usage meters (current_admins/max_admins, current_managers/max_managers, current_operators/max_operators) as progress bars
- **Edit form:** `PUT /api/v1/owner/contracts/{id}` — name, max_admins, max_managers, max_operators, max_storage_gb, price, currency, billing_period, status, payment_status, next_payment_date, grace_period_days, auto_renew, notes, metadata
- **Action buttons:**
  - **Renew:** `POST /api/v1/owner/contracts/{id}/renew` — form: new_end_date*, next_payment_date, new price (optional)
  - **Cancel:** `POST /api/v1/owner/contracts/{id}/cancel` — confirmation dialog

#### Create Contract Form

API: `POST /api/v1/owner/contracts`

- company_id* (searchable dropdown from companies)
- name* (text)
- max_admins (number, default 1, min 1)
- max_managers (number, default 5, min 0)
- max_operators (number, default 10, min 0)
- max_storage_gb (number, default 10, min 1)
- price* (decimal, min 0)
- currency (text, default "USD", 3 chars)
- billing_period (dropdown: monthly, yearly)
- start_date* (date picker)
- end_date* (date picker, must be after start)
- next_payment_date (date picker, optional)
- grace_period_days (number, default 30)
- auto_renew (toggle, default false)
- notes (textarea)

### 11.6 Permissions Reference Page (`/permissions`)

API: `GET /api/v1/owner/permissions`

- **Read-only reference page** showing all available permissions and default permissions for each role
- **Permissions table:** grouped by resource (leads, contacts, deals, tasks, calls, notes, users, stats, settings, company, contract) — shows constant name and string value
- **Role defaults:** Three columns (company_admin, company_manager, company_operator) with checkmarks showing which permissions each role gets by default

### 11.7 Profile Page (`/profile`)

API: `GET /api/v1/owner/auth/me`

- Owner info: first_name, last_name, email (read-only), phone, active status, email verified status
- Change Password section: `POST /api/v1/owner/auth/reset-password`

---

## 12. Shared UI Patterns & Components

### 12.1 Searchable Dropdowns

These fields use **async searchable dropdowns** (typeahead) that search the API:

| Field | Search API | Display Format |
|-------|-----------|---------------|
| `contact_id` (on Lead, Deal) | `GET /api/v1/company/contacts?search=...` | "First Last (phone)" |
| `lead_id` (on Deal) | `GET /api/v1/company/leads?search=...` | "Title" |
| `assigned_to` (on Lead, Deal, Task) | `GET /api/v1/company/users?search=...` | "First Last (role)" |
| `permission_group_id` (on User) | `GET /api/v1/company/permission-groups` | "Group Name" |
| `company_id` (on Contract) | `GET /api/v1/owner/companies` | "Company Name (subdomain)" |

Implementation: Use shadcn `Combobox` component with debounced API search (300ms delay, min 2 chars).

### 12.2 Conditional Form Fields

- **Company create form:** Show different `provider_config` fields based on `provider_type` radio selection (sipuni vs binotel)
- **Task/Note forms:** Show entity search dropdown based on `entity_type` selection (lead/contact/deal/call)
- **User invite form:** Show permission checkboxes OR permission group dropdown (group overrides individual)

### 12.3 Pagination Component

All list endpoints support `?page=1&page_size=20&search=...`. Standard response:

```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8
}
```

Build a reusable `<Pagination>` component: previous/next buttons, page numbers, page size selector (10/20/50/100), "Showing X-Y of Z" text.

### 12.4 Role-Based UI Rendering

Decode JWT to get permissions and role. Build a reusable `hasPermission()` utility and `<PermissionGate>` wrapper component:

```typescript
// Decode JWT to get permissions
const token = localStorage.getItem('access_token');
const payload = JSON.parse(atob(token.split('.')[1]));
const permissions: string[] = payload.permissions;
const role: string = payload.role;

// Check permission
function hasPermission(perm: string): boolean {
  return permissions.includes('*') || permissions.includes(perm);
}

// Wrapper component
function PermissionGate({ permission, children }) {
  return hasPermission(permission) ? children : null;
}

// Usage
<PermissionGate permission="users.create"><InviteUserButton /></PermissionGate>
<PermissionGate permission="leads.write"><CreateLeadButton /></PermissionGate>
<PermissionGate permission="settings.manage"><SettingsLink /></PermissionGate>
```

### 12.5 Status Badges Component

Reusable `<StatusBadge>` with color mapping:

| Entity | Value | Color |
|--------|-------|-------|
| Lead Status | new | blue |
| Lead Status | contacted | yellow |
| Lead Status | qualified | green |
| Lead Status | converted | purple |
| Lead Status | lost | red |
| Deal Stage | prospecting | blue |
| Deal Stage | qualification | cyan |
| Deal Stage | proposal | yellow |
| Deal Stage | negotiation | orange |
| Deal Stage | closed_won | green |
| Deal Stage | closed_lost | red |
| Task Status | pending | gray |
| Task Status | in_progress | blue |
| Task Status | completed | green |
| Task Status | cancelled | red |
| Task Priority | low | gray |
| Task Priority | medium | yellow |
| Task Priority | high | orange |
| Task Priority | urgent | red |
| Call Status | ANSWER | green |
| Call Status | BUSY | orange |
| Call Status | NOANSWER | red |
| Call Status | CANCEL | gray |
| Call Direction | inbound | green |
| Call Direction | outbound | blue |
| Call Direction | internal | gray |
| Contract Status | active | green |
| Contract Status | warning | yellow |
| Contract Status | grace_period | orange |
| Contract Status | expired | red |
| Contract Status | suspended | red |
| Contract Status | cancelled | gray |
| Payment Status | paid | green |
| Payment Status | pending | yellow |
| Payment Status | overdue | red |
| Payment Status | failed | red |
| User Status | active | green |
| User Status | suspended | orange |
| User Status | inactive | gray |
| Provider Type | sipuni | blue |
| Provider Type | binotel | green |

### 12.6 Error Handling

Build a global error handler in Axios interceptor:

| HTTP Status | Meaning | Frontend Action |
|-------------|---------|----------------|
| 400 | Validation error | Show toast with error message |
| 401 | Not authenticated | Attempt token refresh → if fails, redirect to `/login` |
| 403 | Permission denied or password change required | Show error toast; if message contains "Password change required", redirect to `/set-password` |
| 404 | Resource not found | Show "Not Found" page or toast |
| 409 | Conflict (duplicate) | Show inline field error |
| 422 | Pydantic validation error | Parse `detail` array, map to form field errors |
| 500 | Server error | Show generic error toast "Something went wrong" |

422 validation error format:
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "permissions", 0],
      "msg": "Value error, Invalid permissions: [\"invalid.perm\"]",
      "input": "invalid.perm"
    }
  ]
}
```

### 12.7 Empty States

Every list page needs an empty state component with:
- Illustration or icon
- "No {resource} found" message
- "Create your first {resource}" call-to-action button (if user has write permission)

### 12.8 Loading States

- Page-level: skeleton loaders matching the card/table layout
- Button-level: spinner inside buttons during API calls, disable button
- Table/list: skeleton rows

### 12.9 Confirmation Dialogs

All destructive actions (delete, deactivate) show a shadcn `AlertDialog` with:
- Warning icon
- "Are you sure?" message with context (resource name)
- Cancel + Confirm (red) buttons
- Hard delete checkbox for admin actions

### 12.10 Toast Notifications

Use shadcn `toast` for:
- Success: "Contact created successfully", "Deal marked as won"
- Error: API error messages
- Info: "Invitation sent to user@email.com"

---

## 13. Enum Values Reference (for Dropdowns & Badges)

```typescript
// Call
const CallStatus = ["ANSWER", "BUSY", "NOANSWER", "CANCEL", "CONGESTION", "CHANUNAVAIL"];
const CallDirection = ["inbound", "outbound", "internal"];
const CallOutcome = [
  "interested", "appointment_scheduled", "follow_up", "sale_made",
  "no_answer", "left_voicemail", "busy", "callback_requested", "information_provided",
  "not_interested", "wrong_number", "do_not_call", "customer_complaint", "other"
];

// CRM
const LeadStatus = ["new", "contacted", "qualified", "converted", "lost"];
const PipelineStage = ["new", "contact_made", "meeting_scheduled", "proposal_sent", "negotiation", "won", "lost"];
const DealStage = ["prospecting", "qualification", "proposal", "negotiation", "closed_won", "closed_lost"];
const TaskStatus = ["pending", "in_progress", "completed", "cancelled"];
const TaskPriority = ["low", "medium", "high", "urgent"];

// System
const UserRole = ["company_admin", "company_manager", "company_operator"];
const ProviderType = ["sipuni", "binotel"];
const ContractStatus = ["active", "warning", "grace_period", "expired", "suspended", "cancelled"];
const BillingPeriod = ["monthly", "yearly"];
const PaymentStatus = ["paid", "pending", "overdue", "failed"];

// Permissions (all valid values)
const AllPermissions = [
  "leads.read", "leads.write", "leads.delete", "leads.assign",
  "contacts.read", "contacts.write", "contacts.delete", "contacts.import", "contacts.export",
  "deals.read", "deals.write", "deals.delete", "deals.assign",
  "tasks.read", "tasks.write", "tasks.delete", "tasks.assign",
  "calls.read", "calls.write", "calls.make",
  "notes.read", "notes.write", "notes.delete",
  "users.read", "users.create", "users.update", "users.write", "users.delete", "users.manage",
  "stats.read", "stats.export",
  "settings.read", "settings.manage",
  "company.read", "company.manage", "company.delete",
  "contract.read"
];
```

---

## 14. Complete Route Map

### Company Panel Routes

| Route | Page | Component | API Calls |
|-------|------|-----------|-----------|
| `/login` | Login | LoginPage | `POST /auth/login` |
| `/set-password` | Set Password | SetPasswordPage | `POST /auth/set-password` |
| `/forgot-password` | Forgot Password | ForgotPasswordPage | `POST /auth/forgot-password` |
| `/` | Dashboard | DashboardPage | `GET /company/analytics/me/dashboard` or `GET /company/analytics/team/dashboard` |
| `/contacts` | Contacts List | ContactsPage | `GET /company/contacts` |
| `/contacts/:id` | Contact Detail | ContactDetailPage | `GET /company/contacts/:id`, `GET /company/contacts/:id/activity` |
| `/leads` | Leads List | LeadsPage | `GET /company/leads` |
| `/leads/:id` | Lead Detail | LeadDetailPage | `GET /company/leads/:id` |
| `/deals` | Deals Pipeline | DealsPage | `GET /company/deals`, `GET /company/deals/pipeline/summary` |
| `/deals/:id` | Deal Detail | DealDetailPage | `GET /company/deals/:id` |
| `/tasks` | Tasks List | TasksPage | `GET /company/tasks` |
| `/calls` | Call Log | CallsPage | `GET /company/calls` |
| `/calls/:id` | Call Detail | CallDetailPage | `GET /company/calls/:id`, `GET /company/calls/:id/recording` |
| `/notes` | Notes | NotesPage | `GET /company/notes` |
| `/settings/users` | User Management | UsersPage | `GET /company/users` |
| `/settings/users/:id` | User Detail | UserDetailPage | `GET /company/users/:id` |
| `/settings/permission-groups` | Permission Groups | PermissionGroupsPage | `GET /company/permission-groups` |
| `/settings/contract` | Contract Status | ContractPage | `GET /company/contract` |
| `/profile` | My Profile | ProfilePage | `GET /company/users/me`, `PUT /company/users/me` |

### Owner Panel Routes

| Route | Page | Component | API Calls |
|-------|------|-----------|-----------|
| `/login` | Login | OwnerLoginPage | `POST /owner/auth/login` |
| `/set-password` | Set Password | OwnerSetPasswordPage | `POST /owner/auth/set-password` |
| `/forgot-password` | Forgot Password | OwnerForgotPasswordPage | `POST /owner/auth/forgot-password` |
| `/` | Dashboard | OwnerDashboardPage | `GET /owner/analytics/dashboard` |
| `/companies` | Companies List | CompaniesPage | `GET /owner/companies` |
| `/companies/new` | Create Company | CreateCompanyPage | `POST /owner/companies` |
| `/companies/:id` | Company Detail | CompanyDetailPage | `GET /owner/companies/:id` |
| `/contracts` | Contracts List | ContractsPage | `GET /owner/contracts` |
| `/contracts/:id` | Contract Detail | ContractDetailPage | `GET /owner/contracts/:id` |
| `/contracts/new` | Create Contract | CreateContractPage | `POST /owner/contracts` |
| `/permissions` | Permissions Ref | PermissionsRefPage | `GET /owner/permissions` |
| `/profile` | Owner Profile | OwnerProfilePage | `GET /owner/auth/me` |
