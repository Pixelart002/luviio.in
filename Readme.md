# MyStore Backend API

Production-ready e-commerce REST API built with **FastAPI** + **Supabase** + **Stripe**.

[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![Supabase](https://img.shields.io/badge/Supabase-2.9-darkgreen)](https://supabase.com)
[![Stripe](https://img.shields.io/badge/Stripe-10.12-blueviolet)](https://stripe.com)
[![Deploy](https://img.shields.io/badge/Deploy-Koyeb-orange)](https://koyeb.com)

---

## Features

- **Auth** — Register, login, logout, forgot/reset password (Supabase JWT)
- **Products** — CRUD, categories, image upload (WebP optimized), full-text search
- **Orders** — Create, cancel, track — atomic stock management, state machine
- **Payments** — Stripe PaymentIntent, webhook handling (succeeded / failed / canceled)
- **Users** — Profile, address management, admin controls

### Security
- Anti-enumeration on register/forgot-password
- Timing attack mitigation on login (constant response time)
- Magic bytes image validation (content-type spoof protection)
- PIL decompression bomb protection
- UUID validation on all path params (422 not 500)
- PostgrestError global handler (clean single-line logs, no traceback leaks)
- Per-request ID in all logs via `ContextVar`
- Pure ASGI security headers (CSP, HSTS, Referrer-Policy, Permissions-Policy)
- Max body size limit (10MB)
- Rate limiting per real IP (proxy-aware `X-Forwarded-For`)
- Input sanitization (HTML strip on notes field)

### Performance
- Batch product fetch (N+1 fix — single query for all order items)
- Atomic stock deduct via DB RPC (`decrement_stock`)
- GIN full-text search index on products
- DB indexes on `orders.customer_id`, `addresses.user_id`, `stripe_payment_intent`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115 |
| Database | Supabase (PostgreSQL) |
| Auth | Supabase Auth (JWT) |
| Payments | Stripe |
| Email | Resend |
| Images | Pillow → WebP → Supabase Storage |
| Rate Limiting | SlowAPI |
| Deploy | Koyeb (2 workers) |

---

## Project Structure

```
app/
├── __init__.py
├── main.py                  # App factory, middlewares, exception handlers
├── config.py                # Pydantic settings (env vars)
├── dependencies.py          # get_current_user, require_admin
├── supabase_client.py       # Singleton Supabase clients (atomic init)
│
├── routers/
│   ├── __init__.py
│   ├── auth.py              # /auth — register, login, logout, forgot/reset password
│   ├── users.py             # /users — profile, addresses, admin user mgmt
│   ├── products.py          # /products — CRUD, categories, image upload
│   ├── orders.py            # /orders — create, cancel, admin update
│   └── payments.py          # /payments — Stripe intent, webhook
│
├── middlewares/
│   ├── __init__.py
│   └── security.py          # Pure ASGI: HideServer, SecurityHeaders, MaxBodySize
│
└── utils/
    ├── __init__.py
    ├── stock.py             # restore_stock + decrement_stock (RPC + fallback)
    ├── email.py             # Resend email helpers
    └── image.py             # WebP upload helper

migrations.sql               # DB RPCs, indexes, constraints — run once in Supabase
Procfile                     # Koyeb deploy config
requirements.txt
.env.example
```

---

## API Endpoints

### Auth — `/api/v1/auth`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/register` | — | Register (anti-enumeration, always 201) |
| POST | `/login` | — | Login → JWT tokens (constant time response) |
| POST | `/refresh` | — | Refresh access token |
| POST | `/logout` | ✅ | Server-side session invalidate |
| POST | `/forgot-password` | — | Send reset link via email |
| POST | `/reset-password` | ✅ | Update password |

### Users — `/api/v1/users`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/me` | ✅ | Get own profile |
| PATCH | `/me` | ✅ | Update full_name, phone |
| GET | `/me/addresses` | ✅ | List addresses (max 10, default first) |
| POST | `/me/addresses` | ✅ | Add address |
| DELETE | `/me/addresses/{id}` | ✅ | Delete (blocked if active order uses it) |
| GET | `/` | 🔒 Admin | List all users (paginated) |
| PATCH | `/{user_id}` | 🔒 Admin | Update role / is_active |

### Products — `/api/v1`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/products` | — | List (page, search, category, price filter, in_stock) |
| GET | `/products/{slug}` | — | Product detail with images |
| POST | `/products` | 🔒 Admin | Create product |
| PATCH | `/products/{id}` | 🔒 Admin | Update product |
| DELETE | `/products/{id}` | 🔒 Admin | Soft delete (is_active=false) |
| POST | `/products/{id}/image` | 🔒 Admin | Upload image (JPEG/PNG/WebP → optimized WebP) |
| GET | `/categories` | — | List active categories |
| POST | `/categories` | 🔒 Admin | Create category |
| DELETE | `/categories/{id}` | 🔒 Admin | Soft delete (blocked if active products exist) |

### Orders — `/api/v1/orders`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/` | ✅ | Create order (atomic stock, rate limited 10/min) |
| GET | `/my` | ✅ | My orders (paginated) |
| GET | `/my/{id}` | ✅ | Order detail with items |
| POST | `/my/{id}/cancel` | ✅ | Cancel pending order (stock restored) |
| GET | `/` | 🔒 Admin | All orders (status filter, paginated) |
| PATCH | `/{id}` | 🔒 Admin | Update status / tracking number |

**Order status machine:**
```
pending ──→ paid ──→ shipped ──→ delivered
   │                                │
   └──→ cancelled      refunded ←──┘
              ↑
           paid ──→ refunded (Stripe auto-refund)
```

### Payments — `/api/v1/payments`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/create-intent` | ✅ | Create/retrieve Stripe PaymentIntent |
| POST | `/webhook` | Stripe sig | Handle payment events |

**Handled webhook events:**
- `payment_intent.succeeded` → order marked paid, payment record created
- `payment_intent.payment_failed` → stock restored, order cancelled
- `payment_intent.canceled` → stock restored, order cancelled

---

## Setup & Installation

### Prerequisites

- Python 3.13+
- Supabase project (free tier works)
- Stripe account
- Resend account (optional — for confirmation emails)

### 1. Clone & Install

```bash
git clone https://github.com/yourname/store-backend.git
cd store-backend
pip install -r requirements.txt
```

### 2. Environment Variables

Copy `.env.example` to `.env`:

```env
# ── Supabase ──────────────────────────────────────────────────────────────────
SB_URL=https://your-project.supabase.co
SB_KEY=your-anon-key
SB_SERVICE_ROLE_KEY=your-service-role-key

# ── Stripe ────────────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# ── Resend (email) ────────────────────────────────────────────────────────────
RESEND_API_KEY=re_...
FROM_EMAIL=orders@yourstore.com

# ── App ───────────────────────────────────────────────────────────────────────
APP_NAME=MyStore
APP_ENV=development           # development | production
ALLOWED_ORIGINS=https://yourfrontend.com

# ── Pricing (optional — these are defaults) ───────────────────────────────────
SHIPPING_THRESHOLD_STR=75.00
SHIPPING_FLAT_STR=9.99
TAX_RATE_STR=0.08
```

### 3. Database Migrations

Run `migrations.sql` in **Supabase Dashboard → SQL Editor**:

```sql
-- This file creates:
-- 1. increment_stock(p_id, p_qty)  — atomic stock restore (cancel/refund)
-- 2. decrement_stock(p_id, p_qty)  — atomic stock deduct (order create)
-- 3. payments_pi_unique            — webhook replay protection
-- 4. products_slug_unique          — slug uniqueness
-- 5. products_sku_unique_idx       — SKU uniqueness (nullable)
-- 6. fts column + GIN index        — fast full-text search
-- 7. Performance indexes           — customer_id, stripe_pi, address user_id
-- 8. shipping_address_id column    — order traceability
```

### 4. Supabase Dashboard Settings

| Setting | Where | Value |
|---|---|---|
| JWT expiry | Settings → JWT Keys → Legacy JWT Secret | `900` (15 min) |
| Token Rotation | Auth → Sessions → Refresh Tokens | ON |
| Storage bucket | Storage → product-images | Public: ON |

### 5. Set Admin Role

After registering your first admin user:

```sql
-- Supabase SQL Editor
UPDATE users SET role = 'admin' WHERE email = 'your@email.com';
```

### 6. Run Locally

```bash
# Development (auto-reload, docs at /docs)
APP_ENV=development uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## Deploy to Koyeb

**Procfile** (already included):
```
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
```

1. Push repo to GitHub
2. [Koyeb](https://koyeb.com) → New App → Import from GitHub
3. Add all environment variables from `.env.example`
4. Deploy — health check at `/health`

---

## Usage Examples

### Register
```bash
curl -X POST https://your-api.koyeb.app/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Pass@1234", "full_name": "John Doe"}'
```

### Login & save token
```bash
TOKEN=$(curl -s -X POST https://your-api.koyeb.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Pass@1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Browse products
```bash
# List all
curl https://your-api.koyeb.app/api/v1/products

# Search
curl "https://your-api.koyeb.app/api/v1/products?search=phone&min_price=100&in_stock=true"

# Detail
curl https://your-api.koyeb.app/api/v1/products/my-product-slug
```

### Add address
```bash
curl -X POST https://your-api.koyeb.app/api/v1/users/me/addresses \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "line1": "123 MG Road",
    "city": "Mumbai",
    "state": "Maharashtra",
    "postal_code": "400001",
    "country": "IN",
    "is_default": true
  }'
```

### Create order
```bash
curl -X POST https://your-api.koyeb.app/api/v1/orders/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"product_id": "uuid-here", "quantity": 2}
    ],
    "shipping_address_id": "address-uuid-here",
    "notes": "Please pack carefully"
  }'
```

### Upload product image (Admin)
```bash
curl -X POST https://your-api.koyeb.app/api/v1/products/PRODUCT_ID/image \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@/path/to/image.jpg"
```

---

## Request / Response Notes

### Password requirements
- Minimum 8 characters
- At least one uppercase letter
- At least one digit

### Slug format
- Lowercase letters, numbers, hyphens only
- Example: `my-product-name` ✅ — `My Product` ❌

### Country format
- ISO 3166-1 alpha-2 (2 letters)
- Example: `IN`, `US`, `GB`

### Pricing
```
subtotal  = sum(price × quantity)
shipping  = 0            if subtotal >= SHIPPING_THRESHOLD
          = SHIPPING_FLAT otherwise
tax       = (subtotal + shipping) × TAX_RATE
total     = subtotal + shipping + tax
```

---

## Logging

Every request has a unique 8-char ID propagated through all log lines:

```
2026-03-16 09:47:13 | INFO  | [7181c75c] | httpx        | GET /auth/v1/user → 200
2026-03-16 09:47:14 | INFO  | [7181c75c] | httpx        | POST /rpc/decrement_stock → 200
2026-03-16 09:47:15 | INFO  | [7181c75c] | httpx        | POST /rest/v1/orders → 201
2026-03-16 09:47:15 | INFO  | [7181c75c] | httpx        | POST /rest/v1/order_items → 201
2026-03-16 09:47:15 | ERROR | [7181c75c] | app.utils.email | Failed to send confirmation email
```

`X-Request-ID` header is also returned in every HTTP response.

---

## Health Check

```bash
curl https://your-api.koyeb.app/health
# {"status": "ok", "app": "MyStore"}
```

Performs actual Supabase DB ping — returns `503` if database is unreachable.

---

## Security Headers

Every response includes:

```
X-Content-Type-Options:    nosniff
X-Frame-Options:           DENY
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy:   default-src 'none'; frame-ancestors 'none'
Referrer-Policy:           strict-origin-when-cross-origin
Permissions-Policy:        geolocation=(), camera=(), microphone=(), payment=()
```

---

## Roadmap

- [ ] Unit + integration tests (`pytest` + `httpx`)
- [ ] Sentry error monitoring + alerting
- [ ] Cursor-based pagination (large datasets)
- [ ] `create_order_txn` DB RPC (true single-transaction order creation)
- [ ] Supabase JWT custom claims (eliminate per-request DB profile fetch)
- [ ] Multiple product images endpoint (`product_images` table)
- [ ] Order refund flow for customers

---

## License

MIT