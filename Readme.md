Lo bhai! Updated README.md — Luviio branded, complete, professional:

```markdown
# 🛁 Luviio — Luxury Bath & Sanitation E-Commerce API

Production-ready e-commerce REST API built with **FastAPI** + **Supabase** + **Stripe** + **Resend**.

[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![Supabase](https://img.shields.io/badge/Supabase-2.9-darkgreen)](https://supabase.com)
[![Stripe](https://img.shields.io/badge/Stripe-10.12-blueviolet)](https://stripe.com)
[![Resend](https://img.shields.io/badge/Resend-2.5-purple)](https://resend.com)
[![Deploy](https://img.shields.io/badge/Deploy-Koyeb-orange)](https://koyeb.com)

---

## ✨ Features

### 🛒 Core E-Commerce
- **Products** — CRUD, categories, image upload (WebP optimized), full-text search
- **Cart** — Server-side cart with live pricing from DB (tax, shipping, GST)
- **Orders** — Create, cancel, track — atomic stock management, state machine
- **Payments** — Stripe PaymentIntent, webhook handling, idempotency keys
- **Users** — Profile, address management (max 10), admin controls

### 🔔 Notifications
- **Push** — Web Push API (VAPID) for order updates, admin alerts
- **Email** — Resend integration (welcome, order confirmation, shipped, cart reminder)
- **Events** — Observer pattern with background thread pool (non-blocking)

### 🛡️ Security
- Anti-enumeration on register/forgot-password
- Timing attack mitigation on login (constant response time)
- Brute force protection (IP + email blocking with cooldown)
- Magic bytes image validation (content-type spoof protection)
- PIL decompression bomb protection (`MAX_IMAGE_PIXELS = 10M`)
- UUID validation on all path params (422 not 500)
- PostgrestError global handler (clean logs, no traceback leaks)
- Per-request ID in all logs via `ContextVar`
- Pure ASGI security headers (HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy)
- Max body size limit (10MB)
- GZip compression middleware (50-80% bandwidth savings)
- Rate limiting per real IP (proxy-aware: X-Forwarded-For, X-Real-IP, CF-Connecting-IP)
- Input sanitization (HTML strip on notes field)
- Refresh token in HttpOnly cookie (XSS protection)
- CORS strict whitelisting (unknown origins → 403)
- Server header masking (uvicorn → webserver)
- Circuit breaker on push notifications
- Idempotency keys on orders + payments

### ⚡ Performance
- GZip response compression (50-80% savings)
- Batch product fetch (single query for all order items)
- Atomic stock deduct via DB RPC (`decrement_stock`) with 3-tier fallback
- GIN full-text search index on products
- DB indexes on `orders.customer_id`, `addresses.user_id`, `stripe_payment_intent`
- Parallel push notification sending (ThreadPoolExecutor)
- Background email queue with batch flushing
- Pricing_config table for live pricing (no settings.py dependency)

### 📐 Architecture Patterns
- **Strategy Pattern** — Pricing (Standard, ZeroTax, Discount, FreeShipping)
- **Observer Pattern** — Event bus (OrderCreated → AdminPush, OrderPaid → Email+Push)
- **Repository Pattern** — UserRepository, data access abstraction
- **Singleton Pattern** — Supabase clients (thread-safe, double-checked locking)
- **Factory Pattern** — Pricing strategy factory
- **Circuit Breaker** — Push notification failure protection

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115 |
| Database | Supabase (PostgreSQL) |
| Auth | Supabase Auth (JWT + HttpOnly cookies) |
| Payments | Stripe (PaymentIntent + Webhooks) |
| Email | Resend (transactional + batch queue) |
| Push | Web Push API (VAPID) + pywebpush |
| Images | Pillow → WebP → Supabase Storage |
| PDF | ReportLab (GST-compliant invoices) |
| Rate Limiting | SlowAPI |
| Background Tasks | ThreadPoolExecutor |
| Deploy | Koyeb (2 workers) |

---

## 📁 Project Structure

```

app/
├── init.py
├── main.py                  # App factory, middleware stack, lifespan
├── config.py                # Pydantic settings (.env)
├── dependencies.py          # get_current_user, require_admin, get_optional_user
├── supabase_client.py       # Thread-safe singleton Supabase clients
│
├── routers/
│   ├── init.py
│   ├── auth.py              # Register, login, logout, refresh, forgot/reset
│   ├── users.py             # Profile, addresses, admin user management
│   ├── products.py          # CRUD, categories, image upload/reorder/delete
│   ├── orders.py            # Create (idempotent), cancel, admin update
│   ├── payments.py          # Stripe intent, confirm, webhook, brute-force guard
│   ├── cart.py              # Server-side cart with live DB pricing
│   ├── push.py              # Subscribe, unsubscribe, VAPID key, admin batch send
│   ├── invoice.py           # PDF invoice generation + download
│   └── admin_verify.py      # Live DB admin role check (no cache trust)
│
├── services/
│   ├── init.py
│   ├── pricing.py           # Strategy pattern (Standard, ZeroTax, Discount, FreeShipping)
│   ├── events.py            # Event bus (Observer) with retry + dead letter queue
│   └── email_queue.py       # Async email batch queue with dedup + priority
│
├── repositories/
│   ├── init.py
│   └── user_repo.py         # User data access (Repository pattern)
│
├── middlewares/
│   ├── init.py
│   ├── cors.py              # CORS with strict origin whitelisting
│   └── security.py          # RequestID, MaxBodySize, GZip, HideServer, SecurityHeaders
│
└── utils/
├── init.py
├── stock.py             # Atomic stock deduct/restore (RPC + 3 fallbacks)
├── email.py             # Resend email templates (Luviio branded)
├── image.py             # WebP upload/optimize (multiple sizes, validation)
├── push.py              # Web Push API with circuit breaker + retry
└── pdf_invoice.py       # GST-compliant invoice PDF (ReportLab)

.env.example                 # Environment variable template
requirements.txt             # Python dependencies
Procfile                     # Koyeb deploy config

```

---

## 🔌 API Endpoints

### Auth — `/api/v1/auth`

| Method | Endpoint | Auth | Rate Limit | Description |
|---|---|---|---|---|
| POST | `/register` | — | 5/min | Register (anti-enumeration) |
| POST | `/login` | — | 5/min | Login → JWT + HttpOnly cookie |
| POST | `/refresh` | Cookie | 10/min | Refresh access token |
| POST | `/logout` | — | — | Clear session + cookie |
| POST | `/forgot-password` | — | 3/min | Send reset email (anti-enumeration) |
| POST | `/reset-password` | ✅ | — | Update password |
| GET | `/session` | ✅ | — | Check session validity |

### Users — `/api/v1/users`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/me` | ✅ | Get own profile |
| PATCH | `/me` | ✅ | Update full_name, phone |
| GET | `/me/addresses` | ✅ | List addresses (max 10) |
| POST | `/me/addresses` | ✅ | Add address (auto-default first) |
| DELETE | `/me/addresses/{id}` | ✅ | Delete (blocked if active order) |
| GET | `/` | 🔒 Admin | List all users (paginated, search, filter) |
| GET | `/{user_id}` | 🔒 Admin | User detail with order count |
| PATCH | `/{user_id}` | 🔒 Admin | Update role / is_active |

### Products — `/api/v1`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/products` | — | List (page, search, category, price, stock) |
| GET | `/products/{slug}` | — | Product detail with images |
| POST | `/products` | 🔒 Admin | Create product |
| PATCH | `/products/{id}` | 🔒 Admin | Update product |
| DELETE | `/products/{id}` | 🔒 Admin | Soft delete (is_active=false) |
| POST | `/products/{id}/images` | 🔒 Admin | Upload image (→ WebP, max 10) |
| DELETE | `/products/{id}/images/{index}` | 🔒 Admin | Delete image by index |
| PUT | `/products/{id}/images/reorder` | 🔒 Admin | Reorder images |
| GET | `/categories` | — | List active categories |
| POST | `/categories` | 🔒 Admin | Create category |
| DELETE | `/categories/{id}` | 🔒 Admin | Soft delete |

### Cart — `/api/v1/cart`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/` | ✅ | Get cart with live pricing |
| POST | `/items` | ✅ | Add item (or increase quantity) |
| PUT | `/items/{product_id}` | ✅ | Set exact quantity |
| DELETE | `/items/{product_id}` | ✅ | Remove item |
| DELETE | `/` | ✅ | Clear cart |
| GET | `/count` | ✅ | Item count for badge |

### Orders — `/api/v1/orders`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/` | ✅ | Create order (idempotent, rate limited) |
| GET | `/my` | ✅ | My orders (paginated, status filter) |
| GET | `/my/{id}` | ✅ | Order detail with items |
| POST | `/my/{id}/cancel` | ✅ | Cancel pending order (stock restored) |
| GET | `/my/{id}/invoice` | ✅ | Download PDF invoice |
| GET | `/` | 🔒 Admin | All orders (paginated, status filter) |
| PATCH | `/{id}` | 🔒 Admin | Update status / tracking |

**Order State Machine:**
```

pending ──→ paid ──→ shipped ──→ delivered
│         │                      │
└──→ cancelled    refunded ←─────┘
↑
paid ──→ refunded (Stripe auto-refund)

```

### Payments — `/api/v1/payments`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/create-intent` | ✅ | Create/retrieve Stripe PaymentIntent |
| POST | `/confirm` | ✅ | Confirm payment (anti-fraud checks) |
| POST | `/notify-failed` | ✅ | Record payment failure |
| POST | `/webhook` | Stripe sig | Handle Stripe events |

### Push Notifications — `/api/v1/push`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/vapid-key` | — | Get VAPID public key |
| POST | `/subscribe` | ✅ | Subscribe to push (idempotent) |
| DELETE | `/unsubscribe` | ✅ | Unsubscribe |
| GET | `/status` | ✅ | Check subscription status |
| POST | `/admin/send` | 🔒 Admin | Batch send to users |
| GET | `/admin/stats` | 🔒 Admin | Push statistics |

### Admin — `/api/v1/admin`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/verify` | ✅ | Live DB admin check (no cache) |
| GET | `/stats` | 🔒 Admin | Dashboard stats |

### System — `/api/v1`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/pricing/config` | — | Get pricing configuration |
| PUT | `/pricing/config` | 🔒 Admin | Update pricing (DB) |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.13+
- Supabase project
- Stripe account
- Resend account

### 1. Clone & Install
```bash
git clone https://github.com/yourname/luviio-backend.git
cd luviio-backend
pip install -r requirements.txt
```

2. Environment Variables

```bash
cp .env.example .env
# Fill in your values
```

3. Database Setup

Run these in Supabase SQL Editor:

```sql
-- 1. Stock management RPCs
CREATE OR REPLACE FUNCTION decrement_stock(p_id UUID, p_qty INT)
RETURNS SETOF products AS $$
BEGIN
  RETURN QUERY UPDATE products SET stock = stock - p_qty
  WHERE id = p_id AND stock >= p_qty RETURNING *;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION increment_stock(p_id UUID, p_qty INT)
RETURNS SETOF products AS $$
BEGIN
  RETURN QUERY UPDATE products SET stock = stock + p_qty
  WHERE id = p_id RETURNING *;
END;
$$ LANGUAGE plpgsql;

-- 2. Indexes
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_pi ON orders(stripe_payment_intent);
CREATE INDEX IF NOT EXISTS idx_addresses_user ON addresses(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idem ON orders(customer_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

-- 3. Full-text search
ALTER TABLE products ADD COLUMN IF NOT EXISTS fts tsvector GENERATED ALWAYS AS (
  to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))
) STORED;
CREATE INDEX IF NOT EXISTS idx_products_fts ON products USING GIN(fts);

-- 4. Pricing config table
CREATE TABLE IF NOT EXISTS pricing_config (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  tax_rate FLOAT DEFAULT 18.0,
  shipping_flat FLOAT DEFAULT 99.0,
  shipping_threshold FLOAT DEFAULT 999.0,
  currency TEXT DEFAULT 'INR',
  tax_enabled BOOLEAN DEFAULT true,
  shipping_enabled BOOLEAN DEFAULT true,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO pricing_config (tax_rate, shipping_flat, shipping_threshold)
VALUES (18.0, 99.0, 999.0)
ON CONFLICT DO NOTHING;
```

4. Run

```bash
# Development (docs at /docs)
APP_ENV=development uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

---

📊 Pricing Logic

```
subtotal  = Σ (price × quantity)
shipping  = 0 if subtotal ≥ threshold else flat_fee
tax       = (subtotal + shipping) × tax_rate
total     = subtotal + shipping + tax
```

Configurable via pricing_config table (admin panel) or PUT /api/v1/pricing/config.

---

📝 Logging

Every request has a unique 8-char ID propagated through all log lines:

```
2026-06-02 09:47:13 | INFO  | [a1b2c3d4] | POST /orders/ → 201 (45ms)
2026-06-02 09:47:14 | INFO  | [a1b2c3d4] | Stock deducted: product=Grating flower qty=-2
2026-06-02 09:47:15 | WARN  | [e5f6g7h8] | CORS blocked: origin=https://evil.com
```

X-Request-ID header returned in every response.

---

🔒 Security Headers

Every response includes:

```
X-Content-Type-Options:    nosniff
X-Frame-Options:           DENY
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Referrer-Policy:           strict-origin-when-cross-origin
Permissions-Policy:        accelerometer=(), camera=(), geolocation=(), ...
X-XSS-Protection:          0
```

---

🚢 Deploy to Koyeb

```bash
# Procfile (already included)
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
```

1. Push to GitHub
2. Koyeb → New App → Import from GitHub
3. Add all environment variables
4. Deploy — health check at /health

---

📄 License

MIT © 2026 Luviio

```

**Ab README complete hai — professional, detailed, Luviio-branded! 📚**