# System Map

Last reviewed: 2026-09-16

## Runtime topology

```text
Browser / mobile client
        |
        v
   Vercel frontend
        |
        | HTTPS / cookies / JSON
        v
FastAPI application (`app.main:app`)
        |
        +--> request-id / correlation / CORS / security middleware
        +--> maintenance guard
        +--> admin audit middleware
        +--> exception handlers
        |
        +--> `/health*` + `/share/*` infrastructure endpoints
        |
        +--> `/api/v1`
              |
              +--> Auth
              +--> Users
              +--> Products
              +--> Reviews
              +--> Cart
              +--> Coupons
              +--> Shipping
              +--> Pricing (service, not a public router)
              +--> Checkout (orchestration service, not a public router)
              +--> Orders
              +--> Payments
              +--> Inventory
              +--> Notifications
              +--> Subscriptions
              +--> Settings
              +--> RBAC
              +--> Admin
              |
              v
        Domain services
              |
              v
        Domain repositories / policies
              |
        +-----+-------------------+
        |                         |
        v                         v
Supabase/Postgres          External adapters
                          Stripe / email / WebPush / Sentry
```

## Application composition

`app/main.py` is the application factory/runtime composition point. It configures logging and Sentry, starts event handlers and the cron scheduler during lifespan startup, applies shared middleware, registers exception handlers, mounts the infrastructure health and social-share routers, and mounts the versioned API router at `/api/v1`.

`app/api/v1/api.py` is the only versioned router-composition point. It contains route registration only; domain business logic must remain in domain services/policies.

## Layer responsibilities

### Transport
`router.py` validates request DTOs, resolves dependencies, applies permission guards/rate limits, invokes services and shapes the public response.

### Service
`service.py` owns business use-cases, orchestration, invariants, provider coordination and transaction boundaries that are not better expressed as database RPCs.

### Repository
`repository.py` owns persistence access and explicit database projections. Repositories should not contain HTTP concerns.

### Policy / permissions
`app/permissions/*`, RBAC policy modules and dependency helpers define capability checks and protected operations. Ownership checks remain server-side.

### Integrations
Stripe/payment plugins, email, WebPush and Sentry are external boundaries. Business code talks to adapter abstractions instead of provider SDK calls spread throughout routers.

## Domain ownership matrix

| Domain | HTTP | Service | Persistence/policy role | Main responsibility |
|---|---|---|---|---|
| Auth | `/auth/*` | AuthService | auth/session repositories | registration, login, refresh, logout, recovery |
| Users | `/users/*` | UserService | user/address data | profile, addresses, admin user management |
| Products | product/catalog routes | ProductService | product/category/image data | catalog and media |
| Cart | `/cart/*` | CartService | cart repository | active cart lifecycle |
| Pricing | no public router | PricingService | settings/product price inputs | server-side price/tax computation |
| Coupons | `/coupons/*` | CouponService | coupon/redeem data | validation and redemption |
| Shipping | `/shipping/*` | ShippingService | method/rate data | rate calculation and method management |
| Checkout | invoked by Orders/Payments | CheckoutService | composes cart/pricing/shipping/inventory/orders | authoritative checkout orchestration |
| Inventory | `/inventory/*` | InventoryService | stock/activity/order restoration | stock invariants and releases |
| Orders | `/orders/*` | OrderService | order/invoice snapshots | order lifecycle and invoices |
| Payments | `/payments/*` | PaymentService | attempts/ledger/order state | provider payment lifecycle |
| Reviews | `/reviews/*` | ReviewService | product_reviews/order eligibility | moderation and customer reviews |
| Notifications | `/push/*` | PushService | push subscriptions | WebPush registration and delivery |
| Subscriptions | `/subscriptions/*` | SubscriptionService | plan/subscription data | membership tiers |
| Settings | `/settings/*` | AdminSettingsService | system settings | runtime configuration |
| RBAC | `/rbac/*` | role/action control services | permission overrides | role and per-user controls |
| Admin | `/admin/*` | AdminService + plugin manager | analytics/audit/provider config | operator console APIs |
| Health | `/health*` | infrastructure router | DB connectivity | liveness/readiness-style checks |
| Social share | `/share/*` | ProductService dependency | product projection | crawler-readable Open Graph metadata |

## Ownership rule

A domain may call another domain's public service/use-case when the dependency is part of a real business workflow. It should not reach into another domain's repository just to bypass that domain's invariants. Cross-domain persistence coordination that must be atomic belongs in a service/RPC designed for that transaction.

## Canonical commerce chain

```text
Product
  -> Cart
  -> Pricing
  -> Coupon
  -> Shipping
  -> Checkout
  -> Inventory reservation/decrement
  -> Order
  -> Payment (Stripe/COD)
  -> Settlement / ledger
  -> Invoice snapshot/PDF
  -> Notifications / events
```

## Public vs private data

Customer-facing responses must expose customer-facing identifiers such as `order_number`; internal UUIDs, service-role credentials, provider secrets, raw payment data and server-only metadata stay inside trusted server/database boundaries.
