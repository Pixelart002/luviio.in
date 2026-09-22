# Customer/User Flows

Last reviewed: 2026-09-16

## 1. First visit / browse

```text
Browser
  -> frontend catalog page
  -> GET /api/v1/categories
  -> GET /api/v1/products?page=...
  -> GET /api/v1/products/{slug}
  -> optional GET /api/v1/reviews/products/{product_id}
  -> optional /share/products/{slug} for crawler previews
```

Catalog reads are public. Product creation/update/image operations are permission-protected and never performed by the customer browser.

## 2. Registration/login/session

```text
Register
  -> POST /auth/register
  -> Supabase Auth identity
  -> profile metadata
  -> welcome-email event

Login
  -> POST /auth/login
  -> AuthService credential validation
  -> access + refresh HttpOnly cookies

On app reload
  -> GET /auth/session or refresh flow
  -> GET /users/me
  -> frontend reconstructs authenticated state
```

Refresh rotates session cookies. Logout revokes/ends the session and deletes cookies. Recovery uses `/forgot-password` then `/reset-password` with an authenticated recovery context.

## 3. Address lifecycle

```text
GET /users/me/addresses
        |
        +--> POST /users/me/addresses
        |
        +--> DELETE /users/me/addresses/{address_id}
        |
        v
Customer selects shipping/billing context for checkout
```

Address IDs are scoped through the authenticated user context; the client cannot select another customer's address by changing an ID.

## 4. Cart lifecycle

```text
Product detail
  -> POST /cart/items
  -> CartService
      -> product/availability validation
      -> quantity limits
      -> SSOT price calculation
  -> GET /cart
      -> current items + server-calculated values

Quantity change -> PUT /cart/items/{product_id}
Remove          -> DELETE /cart/items/{product_id}
Clear           -> DELETE /cart
```

The frontend must not become the authority for final price, GST, coupon validity, shipping or inventory state.

## 5. Coupon + shipping calculation

```text
Cart subtotal
   |
   +--> POST /coupons/apply
   |       -> coupon rules / redemption constraints
   |
   +--> POST /shipping/rate
           -> method + subtotal + item count + weight + pincode

Final checkout totals
   = product prices
   + shipping
   + applicable product-level GST
   - valid discount
```

The exact final amount is recalculated server-side during checkout; client-calculated values are advisory only.

## 6. Online checkout

```text
Customer clicks Pay
  -> POST /payments/create-intent
      -> provider enabled?
      -> checkout/pricing/address validation
      -> idempotency key
      -> pending order/payment state
      -> provider PaymentIntent
  -> provider UI
  -> POST /payments/confirm
      -> provider status verification
      -> payment settlement
      -> order state transition
      -> inventory settlement
      -> payment attempt/ledger
      -> event/notification
  -> GET /orders/my/{order_number}
```

The public order identifier is `order_number`, not the internal order UUID.

## 7. COD checkout

```text
Customer selects COD
  -> POST /orders/cod
      -> authoritative checkout calculation
      -> inventory/order creation
      -> pending/processing order lifecycle according to service rules
      -> no Stripe PaymentIntent
```

The COD path is intentionally separate from Stripe intent creation.

## 8. Payment retry / cancellation / method switch

Pending order only:

```text
Retry
  -> POST /payments/retry/{order_number}
  -> provider-specific retry

Cancel checkout
  -> POST /payments/cancel/{order_number}
  -> provider status check
  -> provider cancel if needed
  -> inventory restoration exactly once
  -> order cancelled

Switch Stripe <-> COD
  -> POST /payments/switch-method/{order_number}
  -> verify pending state
  -> cancel non-terminal provider intent if necessary
  -> update order method atomically
```

A late provider success must not resurrect an already cancelled order. Payment/order/inventory state machines must converge idempotently.

## 9. Customer order lifecycle

```text
Checkout
  -> customer order number
  -> GET /orders/my
  -> GET /orders/my/{order_number}
  -> optional POST /orders/my/{order_number}/cancel
  -> optional GET /orders/my/{order_number}/invoice
```

Admin updates such as shipped/delivered/refunded are not exposed through customer endpoints.

## 10. Invoice flow

```text
Order
  -> immutable invoice snapshot
       + seller snapshot
       + billing/shipping snapshot
       + item/tax snapshot
       + invoice number
       + QR payload where configured
  -> ReportLab PDF
  -> GET /orders/my/{order_number}/invoice
```

Invoice output is generated from the snapshot, not from mutable current product/settings rows.

## 11. Review flow

```text
Delivered order item
  -> POST /reviews/products/{product_id}
  -> delivered-purchase eligibility query
  -> pending review
  -> admin moderation
       approved -> visible via GET /reviews/products/{product_id}
       rejected -> not public
```

## 12. Push notification flow

```text
GET /push/vapid-key
  -> browser subscription
  -> POST /push/subscribe
  -> GET /push/status
  -> domain event / explicit test
  -> PushService delivery
  -> failure cleanup/retry according to notification policy
```

## Customer trust boundaries

The browser may request an action; it cannot authorize itself. Server-side session identity, permission checks, ownership checks, provider verification and database constraints determine whether the requested action is accepted.
