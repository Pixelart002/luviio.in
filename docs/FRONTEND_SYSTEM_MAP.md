# Luviio Frontend System Map

Last reviewed: 2026-09-24
Source of truth: `frontend/` plus backend domain/API documentation.

## 1. Runtime topology

```text
Browser
  |
  | HTTPS / cookies / JSON
  v
Vercel static frontend (Vite build)
  |
  | frontend/src/api/* 
  v
/api/v1
  |
  v
FastAPI transport
  -> auth/session middleware
  -> permission/ownership checks
  -> domain service
  -> repository / transaction / RPC
  -> Supabase/Postgres
  -> external provider adapters
```

The browser is a presentation/orchestration client. Pricing, tax, inventory authority, authorization, order state, payment state and other business invariants remain server-authoritative.

## 2. Frontend source ownership

```text
frontend/
├── index.html                  # browser document shell
├── package.json                # frontend build/runtime contract
├── vite.config.*               # Vite build
├── src/
│   ├── main.tsx                # React bootstrap + BrowserRouter
│   ├── app/App.tsx             # current route composition
│   ├── api/
│   │   ├── client.ts           # typed browser API surface
│   │   ├── request.ts          # request/error/auth transport helpers
│   │   └── services.ts         # service-style API helpers
│   ├── components/             # reusable UI
│   ├── styles/                 # global/design styles
│   ├── types.ts                # frontend display types
│   └── ...
└── e2e/                        # browser workflows/tests (canonical location)
```

Rules:
- UI components must not call Supabase directly.
- UI components must not recreate backend pricing/GST/shipping logic.
- `src/api/*` is the browser-to-backend boundary.
- Business rules belong in backend domains; browser code consumes authoritative results.
- A workflow is complete only when UI state, API behavior and persistence outcome all agree.

## 3. Current browser route map

| Browser route | Current responsibility | Primary APIs |
|---|---|---|
| `/` | home/catalog discovery | `GET /categories`, `GET /products` |
| `/shop` | catalog/search/filter | `GET /products`, `GET /categories` |
| `/product/:slug` | product detail + add to cart | `GET /products/{slug}`, `POST /cart/items` |
| `/cart` | current cart | `GET /cart`, `PUT/DELETE /cart/items/*`, `DELETE /cart` |
| `/checkout` | address selection + order creation | `GET /users/me/addresses`, `POST /orders/checkout`, `POST /orders/cod` |
| `/orders` | customer order list | `GET /orders/my` |
| `/orders/:orderNumber` | order detail, cancellation, invoice | `GET /orders/my/{order_number}`, `POST /orders/my/{order_number}/cancel`, `GET /orders/{order_number}/invoice` |
| `/account` | login/session/logout | `GET /auth/session`, `POST /auth/login`, `POST /auth/logout` |
| `/register` | registration | `POST /auth/register` |

The route map describes the current frontend code, not an assumed target state.

## 4. Canonical commerce browser chain

```text
Landing
  -> catalog/search
  -> product detail
  -> add to cart
  -> cart validation
  -> sign in / register
  -> address selection
  -> checkout
      -> server pricing
      -> GST/tax
      -> shipping
      -> coupon (when used)
      -> inventory reservation
      -> order creation
      -> payment method
  -> payment / COD result
  -> order confirmation
  -> order history/detail
  -> invoice
  -> delivery / notifications
  -> review
```

The server remains authoritative at each state transition.

## 5. Authentication/session boundary

```text
Browser
  -> login/register
  -> secure session/refresh cookies
  -> authenticated API call
  -> 401/expired-session handling
  -> refresh
  -> retry original safe request
```

Never store service-role credentials or provider secrets in the frontend.

## 6. Browser state rules

### Loading
Every network-backed page has an explicit loading state. Avoid rendering stale partial values as if they were authoritative.

### Success
Show the server-confirmed result, then update local UI state from that result.

### Validation
Client validation is for UX only. API validation remains authoritative.

### 401
Attempt the supported refresh/session recovery path, then redirect to sign-in when recovery fails.

### 403
Show an access-denied state; do not infer permissions from hidden buttons.

### 404
Use a deterministic not-found state for products, orders and routes.

### 409 / concurrency
Show a recoverable conflict state and refetch current server state before retrying.

### 5xx/provider failure
Do not fabricate success. Preserve the user's cart/order context and expose a retry-safe action.

## 7. Missing / incomplete browser surfaces

These backend capabilities need dedicated browser workflows and UI before they can be considered end-to-end complete:

- coupon apply/remove feedback;
- shipping-rate presentation;
- product reviews;
- authenticated route guards;
- admin console and admin authentication/MFA boundary;
- admin product/category/image/measurement workflows;
- inventory adjustment/low-stock views;
- coupon management;
- shipping/fulfillment management;
- settings and RBAC management;
- operational/audit views.

Do not replace a missing backend-connected workflow with mock data just to make a screen appear complete.

## 8. Frontend-to-backend contract rule

For every new page or mutation:

```text
UI requirement
  -> browser workflow ID
  -> API endpoint(s)
  -> DTO/schema
  -> permission/ownership
  -> domain service
  -> persistence/provider
  -> UI success/error states
  -> browser assertion
  -> documentation update
```

The workflow ID should be referenced in the feature PR/commit and in the browser test.

## 9. Documentation ownership

- `docs/SYSTEM_MAP.md`: backend/runtime architecture.
- `docs/API_REFERENCE.md`: endpoint contract and access class.
- `docs/USER_FLOWS.md`: backend customer lifecycle.
- `docs/ADMIN_FLOWS.md`: backend operator lifecycle.
- `docs/FRONTEND_SYSTEM_MAP.md`: browser route + client architecture.
- `docs/BROWSER_WORKFLOWS.md`: executable browser acceptance workflows.

When a route, endpoint, permission, workflow or state transition changes, update the matching source-of-truth document in the same change.
