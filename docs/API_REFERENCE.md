# API Reference — Complete HTTP Inventory

Last reviewed: 2026-09-16

## Counts

- 105 distinct route handlers across the current router modules.
- 106 distinct application handlers after the root `/` health-of-process endpoint.
- 108 concrete URL registrations because health endpoints are mounted both at `/health*` and `/api/v1/health*`.
- Versioned business APIs live under `/api/v1`.
- OpenAPI is available at `/openapi.json`, Swagger UI at `/docs`, ReDoc at `/redoc`.

## Access legend

- **Public**: no authentication/permission dependency.
- **User**: authenticated user/session dependency; ownership is enforced server-side.
- **Permission**: authenticated principal must have the named capability.
- **Webhook**: provider-signed callback; do not treat browser auth as the trust boundary.
- **Infrastructure**: process/database or crawler support endpoint.

## Auth — 7 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Public | Create identity/profile |
| POST | `/api/v1/auth/login` | Public | Authenticate and issue secure cookies |
| POST | `/api/v1/auth/refresh` | Public + refresh cookie | Rotate/refresh session |
| POST | `/api/v1/auth/logout` | Public + refresh cookie | Revoke/sign out |
| POST | `/api/v1/auth/forgot-password` | Public | Start recovery |
| POST | `/api/v1/auth/reset-password` | Bearer recovery context | Set new password |
| GET | `/api/v1/auth/session` | User | Inspect active session |

## Users — 8 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/users/me` | User | Current profile |
| PATCH | `/api/v1/users/me` | User | Update own profile |
| GET | `/api/v1/users/me/addresses` | User | List own addresses |
| POST | `/api/v1/users/me/addresses` | User | Add address |
| DELETE | `/api/v1/users/me/addresses/{address_id}` | User | Delete own address |
| GET | `/api/v1/users/` | `users:read` | Admin user list |
| PATCH | `/api/v1/users/{user_id}` | `users:update` | Admin user mutation |
| GET | `/api/v1/users/{user_id}` | `users:read` | Admin user detail |

## Products/Catalog — 11 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/categories` | Public | Active category list |
| POST | `/api/v1/categories` | `products:create` | Create category |
| DELETE | `/api/v1/categories/{category_id}` | `products:delete` | Delete category |
| GET | `/api/v1/products` | Public | Paginated/search/filter catalog |
| GET | `/api/v1/products/{slug}` | Public | Product detail |
| POST | `/api/v1/products` | `products:create` | Create product, optionally with files |
| PATCH | `/api/v1/products/{product_id}` | `products:update` | Update product |
| DELETE | `/api/v1/products/{product_id}` | `products:delete` | Remove/isolate product |
| POST | `/api/v1/products/{product_id}/images` | `products:update` | Upload images |
| DELETE | `/api/v1/products/{product_id}/images/{index}` | `products:update` | Delete image |
| PUT | `/api/v1/products/{product_id}/images/reorder` | `products:update` | Reorder images |

## Cart — 7 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/cart` | User | Current cart + server-side pricing |
| POST | `/api/v1/cart/items` | User | Add item |
| PUT | `/api/v1/cart/items/{product_id}` | User | Change quantity |
| DELETE | `/api/v1/cart/items/{product_id}` | User | Remove item |
| DELETE | `/api/v1/cart` | User | Clear cart |
| GET | `/api/v1/cart/admin/abandoned` | `cart:view_abandoned` | Abandoned cart list |
| POST | `/api/v1/cart/admin/remind/{cart_id}` | `cart:manage_reminders` | Send reminder |

## Orders — 8 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/v1/orders/checkout` | User | Online checkout/order orchestration |
| POST | `/api/v1/orders/cod` | User | COD order creation |
| GET | `/api/v1/orders/my` | User | Own order list |
| GET | `/api/v1/orders/my/{order_number}` | User/admin owner-aware | Own order detail by public order number |
| POST | `/api/v1/orders/my/{order_number}/cancel` | User | Cancel own eligible order |
| GET | `/api/v1/orders/` | `orders:read` | Global order ledger |
| PATCH | `/api/v1/orders/{order_number}` | `orders:update` | Admin order update |
| GET | `/api/v1/orders/{order_number}/invoice` | User/admin owner-aware | Invoice PDF download |

## Payments — 8 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/api/v1/payments/create-intent` | User | Create provider payment intent |
| POST | `/api/v1/payments/confirm` | User | Confirm/settle client payment |
| POST | `/api/v1/payments/retry/{order_number}` | User + ownership | Retry pending payment |
| POST | `/api/v1/payments/cancel/{order_number}` | User + ownership | Safely cancel checkout payment and restore stock |
| POST | `/api/v1/payments/switch-method/{order_number}` | User + ownership | Switch pending Stripe/COD method |
| POST | `/api/v1/payments/notify-failed` | User | Record client-side failure |
| POST | `/api/v1/payments/webhook` | Provider signature | Stripe compatibility webhook |
| POST | `/api/v1/payments/webhook/{provider_key}` | Provider signature | Generic provider webhook |

## Inventory — 6 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/inventory/stock/{product_id}` | Publicly callable | Current stock projection |
| POST | `/api/v1/inventory/admin/adjust` | `inventory:adjust` | Atomic stock adjustment + audit |
| GET | `/api/v1/inventory/availability/{product_id}` | Publicly callable | Availability check |
| GET | `/api/v1/inventory/low-stock` | Publicly callable in current code | Low-stock list |
| POST | `/api/v1/inventory/low-stock/scan` | Publicly callable in current code | Scan/publish alerts |
| POST | `/api/v1/inventory/stale-orders/release` | Publicly callable in current code | Release stale pending orders |

The last three are operational endpoints and should be treated as protected operational surfaces in production hardening if they are reachable outside trusted infrastructure.

## Coupons — 5 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/coupons/manage` | `coupons:read` | Admin list |
| POST | `/api/v1/coupons/manage` | `coupons:create` | Create |
| PATCH | `/api/v1/coupons/manage/{coupon_id}` | `coupons:update` | Update |
| DELETE | `/api/v1/coupons/manage/{coupon_id}` | `coupons:delete` | Delete |
| POST | `/api/v1/coupons/apply` | `coupons:apply` + User | Validate/apply to cart subtotal |

## Shipping — 5 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/shipping/methods` | `shipping:read` | Active/all methods |
| POST | `/api/v1/shipping/rate` | `shipping:read` | Compute shipping rate |
| POST | `/api/v1/shipping/manage` | `shipping:update` | Create method |
| PATCH | `/api/v1/shipping/manage/{method_id}` | `shipping:update` | Update method |
| POST | `/api/v1/shipping/manage/{method_id}/activate` | `shipping:update` | Activate method |

## Reviews — 5 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/reviews/products/{product_id}` | Public | Approved reviews |
| POST | `/api/v1/reviews/products/{product_id}` | User | Submit review; delivered purchase eligibility is checked |
| GET | `/api/v1/reviews/me` | User | Own reviews |
| GET | `/api/v1/reviews/admin` | `reviews:moderate` | Moderation queue |
| PATCH | `/api/v1/reviews/admin/{review_id}` | `reviews:moderate` | Approve/reject/pending |

## Notifications / Push — 7 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/push/vapid-key` | Public | WebPush public key |
| POST | `/api/v1/push/subscribe` | User | Register subscription |
| DELETE | `/api/v1/push/unsubscribe` | User | Remove subscription |
| GET | `/api/v1/push/status` | User | Subscription status |
| POST | `/api/v1/push/test` | User | Test notification |
| POST | `/api/v1/push/admin/send` | `admin:manage_settings` | Batch send |
| GET | `/api/v1/push/admin/stats` | `admin:view_analytics` | Push statistics |

## Settings — 3 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/settings/` | `settings:read` | Read settings |
| GET | `/api/v1/payments/public-config` | Public | Browser-safe payment configuration only |
| PATCH | `/api/v1/settings/{key}` | `settings:update` | Mutate setting with reason/context |
| POST | `/api/v1/settings/{key}/reset` | `settings:reset` | Restore default |

## RBAC — 8 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/rbac/permissions/catalogue` | `admin:manage_roles` | Permission catalogue |
| GET | `/api/v1/rbac/permissions` | `admin:manage_roles` | Effective matrix + overrides |
| POST | `/api/v1/rbac/permissions/toggle` | `admin:manage_roles` | Toggle role permission |
| DELETE | `/api/v1/rbac/permissions/{role}/{permission}` | `admin:manage_roles` | Remove override |
| GET | `/api/v1/rbac/users/{user_id}/actions` | `admin:manage_roles` | Per-user controls |
| POST | `/api/v1/rbac/users/{user_id}/actions` | `admin:manage_roles` | Set per-user control |
| DELETE | `/api/v1/rbac/users/{user_id}/actions/{action}` | `admin:manage_roles` | Remove control |
| GET | `/api/v1/rbac/users/{user_id}/actions/{action}/enabled` | `admin:manage_roles` | Live action check |

## Subscriptions — 6 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/subscriptions/plans` | `subscriptions:read_plans` | Plans |
| GET | `/api/v1/subscriptions/plans/public` | `subscriptions:read_plans` | Public tiers |
| POST | `/api/v1/subscriptions/plans` | `subscriptions:manage` | Create plan |
| PUT | `/api/v1/subscriptions/plans/{plan_id}` | `subscriptions:manage` | Update plan |
| POST | `/api/v1/subscriptions/subscribe` | User + `subscriptions:subscribe` | Subscribe |
| GET | `/api/v1/subscriptions/me` | User + `subscriptions:read_mine` | Current membership |

## Admin — 13 handlers

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/admin/verify` | `admin:access_console` | Verify console access |
| GET | `/api/v1/admin/stats` | `admin:view_analytics` | Dashboard metrics |
| GET | `/api/v1/admin/reports/summary` | `admin:view_analytics` | Report summary |
| GET | `/api/v1/admin/payments` | `admin:view_analytics` | Payment ledger view |
| GET | `/api/v1/admin/audit` | `admin:view_analytics` | Audit log view |
| GET | `/api/v1/admin/payment-plugins` | `admin:manage_settings` | Providers |
| GET | `/api/v1/admin/payment-plugins/methods` | `admin:manage_settings` | Payment methods |
| PATCH | `/api/v1/admin/payment-plugins/{provider_key}` | `admin:manage_settings` | Enable/disable provider |
| PATCH | `/api/v1/admin/payment-plugins/{provider_key}/methods/{method_key}` | `admin:manage_settings` | Enable/disable method |
| POST | `/api/v1/admin/payment-plugins` | `admin:manage_settings` | Register provider |
| POST | `/api/v1/admin/payment-plugins/{provider_key}/methods` | `admin:manage_settings` | Register method |
| POST | `/api/v1/admin/payment-plugins/{provider_key}/default` | `admin:manage_settings` | Set default provider |
| DELETE | `/api/v1/admin/payment-plugins/{provider_key}` | `admin:manage_settings` | Remove provider config; history preserved |

## Infrastructure — 4 handlers, 5 URL registrations

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/health/live` | Infrastructure | Process liveness |
| GET | `/health` | Infrastructure | DB-backed health |
| GET | `/api/v1/health/live` | Infrastructure | Same liveness handler through versioned mount |
| GET | `/api/v1/health` | Infrastructure | Same DB health handler through versioned mount |
| GET | `/share/products/{slug}` | Public crawler | Server-rendered Open Graph share page |

The root `/` application endpoint is not included in the versioned API and returns process reachability metadata.

## API workflow classes

### Read path
`HTTP -> auth/permission dependency -> service -> repository -> Supabase -> safe projection -> response`

### Mutation path
`HTTP -> DTO validation -> auth/permission -> service invariant -> repository/RPC -> event/audit -> response`

### Payment webhook
`Provider -> signed webhook -> provider adapter -> PaymentService -> idempotent settlement -> order/inventory/ledger -> event`

### Admin mutation
`Admin UI -> permission -> service -> repository/integration -> audit action -> response`
