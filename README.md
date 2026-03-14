# 🛒 Store Backend API

Production-grade Python e-commerce backend built with FastAPI.

## Stack

| Layer        | Technology                                |
|-------------|-------------------------------------------|
| Framework    | FastAPI 0.115                             |
| ORM          | SQLAlchemy 2.0                            |
| Database     | PostgreSQL (SQLite for dev/testing)       |
| Auth         | JWT (access + refresh tokens)             |
| Passwords    | bcrypt via passlib                        |
| Payments     | Stripe                                    |
| Rate Limiting| slowapi                                   |
| Validation   | Pydantic v2                               |

## Project Structure

```
store_backend/
├── app/
│   ├── main.py          # App factory, middleware, lifespan
│   ├── config.py        # Settings from .env
│   ├── database.py      # SQLAlchemy engine + session
│   ├── models.py        # ORM models
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── security.py      # JWT + bcrypt helpers
│   ├── dependencies.py  # FastAPI dependency injection
│   └── routers/
│       ├── auth.py      # /auth/*
│       ├── users.py     # /users/*
│       ├── products.py  # /products/*, /categories/*
│       ├── orders.py    # /orders/*
│       └── payments.py  # /payments/*
├── requirements.txt
├── alembic.ini
└── .env.example
```

## Security Features

- ✅ JWT access tokens (30 min) + refresh tokens (7 days)
- ✅ bcrypt password hashing
- ✅ Role-based access control (admin / customer)
- ✅ Rate limiting (60 req/min per IP, configurable)
- ✅ CORS with explicit origin allowlist
- ✅ Input validation via Pydantic (length, regex, ranges)
- ✅ Row-level DB locking to prevent overselling
- ✅ Stripe webhook signature verification
- ✅ SQL injection protection via SQLAlchemy ORM
- ✅ Docs hidden in production (`APP_ENV=production`)
- ✅ Soft delete for products (preserves order history)

## Setup

```bash
# 1. Clone and install
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your DB URL, SECRET_KEY, Stripe keys, etc.

# 3. Run (development)
APP_ENV=development uvicorn app.main:app --reload --port 8000

# 4. Run (production)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

For a quick local test without PostgreSQL, set:
```
DATABASE_URL=sqlite:///./store.db
```

---

## API Reference & curl Examples

> Set these variables once and reuse them:
> ```bash
> BASE="http://localhost:8000/api/v1"
> # After login, set:
> TOKEN="<access_token>"
> ADMIN_TOKEN="<admin_access_token>"
> ```

---

### 🔍 Health Check

```bash
curl http://localhost:8000/health
```

---

### 🔐 Auth

#### Register a new customer

```bash
curl -s -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "Secret123",
    "full_name": "Alice Smith"
  }' | jq
```

#### Login (returns access + refresh token)

```bash
curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice@example.com&password=Secret123" | jq

# Save the token:
TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice@example.com&password=Secret123" \
  | jq -r '.access_token')
echo "Token: $TOKEN"
```

#### Refresh access token

```bash
curl -s -X POST "$BASE/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<your_refresh_token>"}' | jq
```

#### Login as admin (seeded on first startup)

```bash
ADMIN_TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@mystore.com&password=change-me" \
  | jq -r '.access_token')
```

---

### 👤 Users

#### Get my profile

```bash
curl -s "$BASE/users/me" \
  -H "Authorization: Bearer $TOKEN" | jq
```

#### Update my profile / change password

```bash
curl -s -X PATCH "$BASE/users/me" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name": "Alice Johnson", "password": "NewPass456"}' | jq
```

#### Add a shipping address

```bash
curl -s -X POST "$BASE/users/me/addresses" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "line1": "123 Main Street",
    "city": "New York",
    "state": "NY",
    "postal_code": "10001",
    "country": "US",
    "is_default": true
  }' | jq

# Save address ID:
ADDRESS_ID=$(curl -s "$BASE/users/me/addresses" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.[0].id')
```

#### List my addresses

```bash
curl -s "$BASE/users/me/addresses" \
  -H "Authorization: Bearer $TOKEN" | jq
```

#### Delete an address

```bash
curl -s -X DELETE "$BASE/users/me/addresses/$ADDRESS_ID" \
  -H "Authorization: Bearer $TOKEN" -w "%{http_code}"
```

#### [Admin] List all users

```bash
curl -s "$BASE/users/?skip=0&limit=20" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq
```

#### [Admin] Deactivate a user

```bash
curl -s -X PATCH "$BASE/users/<user_id>" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}' | jq
```

#### [Admin] Promote user to admin

```bash
curl -s -X PATCH "$BASE/users/<user_id>" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}' | jq
```

---

### 📦 Products & Categories

#### List categories

```bash
curl -s "$BASE/categories" | jq
```

#### [Admin] Create a category

```bash
curl -s -X POST "$BASE/categories" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Electronics",
    "slug": "electronics",
    "description": "Gadgets and devices"
  }' | jq
```

#### List products (paginated)

```bash
curl -s "$BASE/products?page=1&page_size=10" | jq
```

#### List products with filters

```bash
# By category slug
curl -s "$BASE/products?category=electronics" | jq

# Search by name
curl -s "$BASE/products?search=headphone" | jq

# Price range + in stock only
curl -s "$BASE/products?min_price=10&max_price=200&in_stock=true" | jq

# Combined
curl -s "$BASE/products?category=electronics&search=phone&min_price=50&page=1&page_size=5" | jq
```

#### Get a single product by slug

```bash
curl -s "$BASE/products/my-awesome-product" | jq
```

#### [Admin] Create a product

```bash
curl -s -X POST "$BASE/products" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Wireless Headphones",
    "slug": "wireless-headphones",
    "description": "Over-ear noise-cancelling headphones",
    "price": "79.99",
    "compare_price": "129.99",
    "sku": "WH-001",
    "stock": 50,
    "is_active": true,
    "image_url": "https://cdn.mystore.com/wh-001.jpg",
    "weight_grams": 280
  }' | jq

# Save product ID for later:
PRODUCT_ID=$(curl -s "$BASE/products/wireless-headphones" | jq -r '.id')
```

#### [Admin] Update a product (partial)

```bash
curl -s -X PATCH "$BASE/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"price": "69.99", "stock": 45}' | jq
```

#### [Admin] Restock a product

```bash
curl -s -X PATCH "$BASE/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"stock": 100}' | jq
```

#### [Admin] Soft-delete a product

```bash
curl -s -X DELETE "$BASE/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -w "%{http_code}"
```

---

### 🧾 Orders

#### Create an order

```bash
curl -s -X POST "$BASE/orders/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"items\": [
      {\"product_id\": \"$PRODUCT_ID\", \"quantity\": 2}
    ],
    \"shipping_address_id\": \"$ADDRESS_ID\",
    \"notes\": \"Please gift wrap\"
  }" | jq

# Save order ID:
ORDER_ID=$(curl -s -X POST "$BASE/orders/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"items\":[{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}],\"shipping_address_id\":\"$ADDRESS_ID\"}" \
  | jq -r '.id')
```

#### List my orders

```bash
curl -s "$BASE/orders/my?skip=0&limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq
```

#### Get a specific order

```bash
curl -s "$BASE/orders/my/$ORDER_ID" \
  -H "Authorization: Bearer $TOKEN" | jq
```

#### Cancel an order (only when status=pending)

```bash
curl -s -X POST "$BASE/orders/my/$ORDER_ID/cancel" \
  -H "Authorization: Bearer $TOKEN" | jq
```

#### [Admin] List all orders

```bash
curl -s "$BASE/orders/?page=1&page_size=20" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq

# Filter by status
curl -s "$BASE/orders/?status_filter=paid" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq
```

#### [Admin] Mark order as shipped + add tracking

```bash
curl -s -X PATCH "$BASE/orders/$ORDER_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "shipped", "tracking_number": "1Z999AA10123456784"}' | jq
```

#### [Admin] Mark order as delivered

```bash
curl -s -X PATCH "$BASE/orders/$ORDER_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "delivered"}' | jq
```

---

### 💳 Payments (Stripe)

#### Create a payment intent for an order

```bash
curl -s -X POST "$BASE/payments/create-intent" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"order_id\": \"$ORDER_ID\"}" | jq
# Returns client_secret — use this in your frontend with Stripe.js
```

#### Simulate Stripe webhook (test)

```bash
# Use the Stripe CLI to forward webhooks in development:
# stripe listen --forward-to localhost:8000/api/v1/payments/webhook

# Or manually send a test event:
curl -s -X POST "$BASE/payments/webhook" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: t=1234,v1=fake" \
  -d '{"type": "payment_intent.succeeded"}' | jq
# Note: real webhook calls will be rejected if signature is wrong (security feature)
```

---

## Order Status Flow

```
pending ──(pay)──► paid ──(ship)──► shipped ──(deliver)──► delivered
   │
   └──(cancel)──► cancelled
```

## Pricing Logic

- Free shipping on orders ≥ $75.00
- Flat $9.99 shipping otherwise
- 8% tax applied on (subtotal + shipping)

## Running Tests

```bash
pip install pytest pytest-asyncio httpx
# Set test DB:
export DATABASE_URL=sqlite:///./test.db
pytest tests/ -v
```

## Production Checklist

- [ ] Set `APP_ENV=production` (hides /docs, /redoc)
- [ ] Use a strong random `SECRET_KEY` (`openssl rand -hex 32`)
- [ ] Set `ALLOWED_ORIGINS` to your actual frontend domain(s)
- [ ] Use PostgreSQL, not SQLite
- [ ] Run behind a reverse proxy (nginx/Caddy) with TLS
- [ ] Use Alembic for DB migrations (`alembic upgrade head`)
- [ ] Configure Stripe webhook endpoint in the Stripe dashboard
- [ ] Set up structured logging (e.g. structlog)
- [ ] Monitor with Sentry or similar
