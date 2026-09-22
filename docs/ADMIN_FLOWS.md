# Admin and Operator Flows

Last reviewed: 2026-09-16

## Admin access

```text
Login/session
   -> permission resolution
   -> GET /api/v1/admin/verify
   -> Admin console
```

Console access is capability-based. UI visibility is not a security boundary; each API route enforces its own permission.

## 1. Dashboard and operations

```text
Admin console
  -> GET /admin/stats
  -> GET /admin/reports/summary
  -> GET /admin/payments
  -> GET /admin/audit
```

Analytics/read permissions are distinct from mutation permissions.

## 2. Catalog management

```text
Categories
  GET  /categories
  POST /categories           [products:create]
  DELETE /categories/{id}    [products:delete]

Products
  GET  /products
  GET  /products/{slug}
  POST /products              [products:create]
  PATCH /products/{id}        [products:update]
  DELETE /products/{id}       [products:delete]

Images
  POST /products/{id}/images             [products:update]
  DELETE /products/{id}/images/{index}   [products:update]
  PUT /products/{id}/images/reorder      [products:update]
```

Product create accepts JSON or multipart with image files. The ProductService remains responsible for validation, storage and product persistence.

## 3. User administration

```text
GET   /users/             [users:read]
GET   /users/{user_id}    [users:read]
PATCH /users/{user_id}    [users:update]
```

Admin mutations must pass through UserService so audit/role and ownership-related policies are not bypassed.

## 4. Inventory operations

```text
GET  /inventory/stock/{product_id}
POST /inventory/admin/adjust              [inventory:adjust]
GET  /inventory/availability/{product_id}
GET  /inventory/low-stock
POST /inventory/low-stock/scan
POST /inventory/stale-orders/release
```

`admin/adjust` is the explicit stock mutation. It is documented as atomic and audit-producing. Operational scan/release endpoints should be restricted to trusted operators/jobs before external exposure.

## 5. Orders

```text
GET   /orders/                         [orders:read]
PATCH /orders/{order_number}           [orders:update]
GET   /orders/{order_number}/invoice  owner/admin-aware
```

Admin order mutation is payment-aware through `OrderPaymentPort` and must preserve legal/state-machine invariants.

## 6. Payments and provider management

Read:

```text
GET /admin/payments
GET /admin/payment-plugins
GET /admin/payment-plugins/methods?provider_key=stripe
```

Mutation:

```text
PATCH /admin/payment-plugins/{provider_key}
PATCH /admin/payment-plugins/{provider_key}/methods/{method_key}
POST  /admin/payment-plugins
POST  /admin/payment-plugins/{provider_key}/methods
POST  /admin/payment-plugins/{provider_key}/default
DELETE /admin/payment-plugins/{provider_key}
```

Provider registration leaves the provider disabled until explicitly enabled. Historical payments remain when a provider is removed from runtime configuration.

## 7. Coupon operations

```text
GET    /coupons/manage              [coupons:read]
POST   /coupons/manage              [coupons:create]
PATCH  /coupons/manage/{id}         [coupons:update]
DELETE /coupons/manage/{id}         [coupons:delete]
```

Coupon application itself is a customer operation but is permission-guarded by `coupons:apply` and authenticated user ownership.

## 8. Shipping operations

```text
GET  /shipping/methods
POST /shipping/rate
POST /shipping/manage
PATCH /shipping/manage/{id}
POST /shipping/manage/{id}/activate
```

There is intentionally no hard-delete route for shipping methods because old orders may reference historical configurations.

## 9. Settings operations

```text
GET  /settings/
PATCH /settings/{key}       [settings:update]
POST /settings/{key}/reset  [settings:reset]
```

A setting update records actor/reason context and invalidates the maintenance cache. Settings are operational configuration, not secret storage.

## 10. RBAC and fine-grained controls

Role-level:

```text
GET    /rbac/permissions/catalogue
GET    /rbac/permissions
POST   /rbac/permissions/toggle
DELETE /rbac/permissions/{role}/{permission}
```

Per-user action controls:

```text
GET    /rbac/users/{user_id}/actions
POST   /rbac/users/{user_id}/actions
DELETE /rbac/users/{user_id}/actions/{action}
GET    /rbac/users/{user_id}/actions/{action}/enabled
```

The RBAC policy prevents administrator self-lockout and limits which roles can be managed by the current actor.

## 11. Review moderation

```text
GET   /reviews/admin?status_filter=pending
PATCH /reviews/admin/{review_id}
```

Moderation changes status; only approved reviews are exposed publicly.

## 12. Push/notification operations

```text
POST /push/admin/send
GET  /push/admin/stats
```

Batch send requires an admin capability. Notification failure should be observable separately from the business transaction that produced the event.

## 13. Subscription administration

```text
GET  /subscriptions/plans
GET  /subscriptions/plans/public
POST /subscriptions/plans
PUT  /subscriptions/plans/{plan_id}
```

Plan management is separate from customer subscription purchase.

## 14. Standard admin mutation lifecycle

```text
Admin UI
  -> authenticated session
  -> permission dependency
  -> DTO/schema validation
  -> domain service
  -> repository/integration
  -> audit/action record when applicable
  -> safe response
```

The UI must never implement authorization by hiding buttons alone. The API is the final authority.
