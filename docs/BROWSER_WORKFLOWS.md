# Luviio Browser Workflows

Last reviewed: 2026-09-24
Purpose: executable, production-oriented acceptance map for real browser behavior.

## 0. Browser test contract

Every workflow has:
- Preconditions
- Browser actions
- Network/API boundary
- Expected UI result
- Failure/recovery assertions
- Cleanup or test-data rule

Use stable semantic selectors (`role`, accessible name, labels, and explicit `data-testid` only where needed). Do not use CSS class names as the primary automation contract.

Browser tests must never weaken server authorization. A passing UI test is insufficient when the API would reject the same operation.

## 1. Smoke workflows

### BW-001 — App shell
Precondition: deployment is reachable.
1. Open `/`.
2. Wait for the document and main content.
3. Verify no fatal console error.
4. Verify primary navigation is visible.
5. Verify catalog content either loads or shows a deliberate empty/error state.

Pass: page is usable and has no unhandled application failure.

### BW-002 — Public catalog
1. Open `/shop`.
2. Verify product listing or deliberate empty state.
3. Search using the header/search UI.
4. Verify URL/query and displayed results correspond.
5. Open one product.

Pass: public catalog is navigable without authentication.

### BW-003 — Product detail
1. Open a valid `/product/:slug`.
2. Verify name, price and primary image/content.
3. Verify add-to-cart control.
4. Add one unit.
5. Verify success state and navigate to cart.

Pass: product detail consumes live API data and produces a server-backed cart mutation.

## 2. Authentication workflows

### BW-010 — Registration
1. Open `/register`.
2. Submit valid unique test credentials.
3. Verify success response/state.
4. Navigate to sign-in.

Assertions:
- invalid email/password is rejected;
- duplicate identity is shown as a recoverable error;
- no password/token is exposed in UI or logs.

### BW-011 — Login/session
1. Open `/account`.
2. Submit valid credentials.
3. Verify authenticated state.
4. Refresh the browser.
5. Verify session remains valid through the supported cookie/session mechanism.
6. Sign out.
7. Verify protected data is no longer accessible.

### BW-012 — Expired-session recovery
Precondition: test session can be expired/revoked.
1. Start authenticated.
2. Trigger a protected API call after expiry.
3. Verify refresh/recovery path runs.
4. Retry the original safe request.
5. If recovery fails, redirect to sign-in with no loop.

## 3. Cart workflows

### BW-020 — Add/update/remove canonical cart
1. Add a product to the cart.
2. Open `/cart`.
3. Verify each line uses the backend cart DTO: name, image_url, quantity, unit_price and line_total.
4. Change quantity and verify the API result updates the rendered line and totals.
5. Remove the line and verify the empty-cart state.

Assertions:
- `CartResponse.total_amount`, `subtotal` and `tax_amount` are rendered from server data.
- `has_unavailable_items` blocks checkout.
- `price_changed` is surfaced to the customer.
- Shipping is explicitly marked as calculated at checkout rather than fabricated from a frontend rate.

### BW-021 — Cart authorization
1. Open `/cart` signed out.
2. Verify deterministic sign-in/recovery UX.
3. Sign in and reload the cart.
4. Verify only the authenticated user's cart is visible.

## 4. Checkout workflows

### BW-030 — Address prerequisite
1. Start from a non-empty cart.
2. Open `/checkout`.
3. Verify saved/default addresses load.
4. Add a new address.
5. Verify the new address becomes selected.
6. Verify the address PIN is the input for live shipping serviceability.

### BW-031 — Live shipping selection
1. Select a delivery address.
2. Verify `GET /shipping/provider/rate` is called with the delivery PIN, canonical cart weight and declared cart value.
3. Verify courier name, service, ETA and live shipping charge are visible.
4. Select a courier.
5. Switch between online and COD.
6. Verify shipping options are refreshed because COD serviceability can differ.
7. Verify the selected courier ID is carried into the final order/payment request.

Assertions:
- Browser does not calculate or hard-code the authoritative shipping charge.
- Provider failure leaves checkout in a retryable state.
- No courier option is treated as a successful checkout prerequisite.

### BW-032 — Online checkout
1. Select address and a serviceable courier.
2. Select online payment.
3. Submit `POST /payments/create-intent` with the selected courier ID.
4. Complete Stripe confirmation.
5. Verify `POST /payments/confirm` succeeds.
6. Clear the cart only after confirmation.
7. Navigate to `/orders/:orderNumber` using the server-confirmed public order number.

### BW-033 — COD checkout
1. Select address and a COD-compatible courier.
2. Submit `POST /orders/cod` with the selected courier ID.
3. Clear the cart only after order creation succeeds.
4. Navigate to the server-confirmed order number.

### BW-034 — Checkout failure/recovery
Trigger an address, stock, shipping-provider, payment-provider or validation failure.
Verify:
- no false success;
- selected cart/order context is preserved;
- the user gets an actionable error;
- a retry does not create a duplicate order.

## 5. Payment workflows

### BW-040 — Payment success/failure
- Successful provider confirmation must produce an authoritative order state.
- Failed card confirmation must not show success and must notify the backend of payment failure.
- Missing Stripe browser configuration must stop the online path before attempting provider confirmation.

## 6. Order lifecycle workflows

### BW-050 — Order history
1. Sign in.
2. Open `/orders`.
3. Verify the list consumes `order_number`, `status`, `total_amount` and `created_at`.
4. Open an order by its public order number.

### BW-051 — Order detail
1. Open `/orders/:orderNumber`.
2. Verify items come from `order_items`.
3. Verify summary uses `subtotal`, `shipping_cost`, `tax_amount`, `discount_amount` and `total_amount`.
4. Verify the shipping address snapshot is visible.
5. Verify courier, service and AWB/tracking information when available.
6. Verify `GET /shipping/my/:orderNumber` drives shipment status/tracking data.
7. Verify a not-yet-booked shipment renders a deliberate pending state.

### BW-052 — Shipment tracking
1. Open an order with a provider shipment.
2. Verify courier and AWB.
3. Verify tracking URL when returned.
4. Verify the order timeline distinguishes order state from granular shipment workflow state.

### BW-053 — Invoice
1. Open an eligible order.
2. Trigger invoice download.
3. Verify the PDF request uses the public order number and the authenticated session.
4. Verify a failed download leaves the order page usable.

### BW-054 — Cancellation
1. Open a cancellable order.
2. Confirm cancellation.
3. Verify the cancel response is not treated as a complete order object.
4. Refetch order + shipment.
5. Verify the updated authoritative status and cancellation action state.

## 7. Product and customer interaction workflows

### BW-060 — Product image/media
1. Open product detail.
2. Verify primary image, alt text and fallback.
3. Test a product with multiple images when supported.

### BW-061 — Review
1. Sign in as an eligible delivered customer.
2. Open product/order review surface.
3. Submit review.
4. Verify moderation/status state.
5. Verify ineligible users are rejected by the API and UI handles that response.

### BW-062 — Coupon
1. Add eligible items.
2. Enter a valid coupon.
3. Verify server-confirmed discount.
4. Try invalid/expired/ineligible coupon.
5. Verify no client-side discount spoofing changes the authoritative total.

## 8. Admin browser workflows

### BW-100 — Admin access
1. Open admin entry point.
2. Authenticate with an authorized admin.
3. Verify `/admin/verify` authorization result.
4. Verify unauthorized users are denied.
5. Verify MFA/AAL requirements are respected where enforced.

### BW-101 — Product CRUD
1. Open product management.
2. Create a product with valid canonical fields.
3. Upload/reorder/delete images.
4. Configure the single canonical measurement type/fields used by the backend.
5. Save.
6. Verify public catalog reflects the server response.
7. Update product.
8. Delete/deactivate according to backend policy.

### BW-102 — Inventory
1. Open inventory/admin stock workflow.
2. Adjust stock with reason.
3. Verify server-confirmed stock.
4. Verify low-stock state when threshold is crossed.
5. Verify unauthorized mutation is rejected.

### BW-103 — Orders/admin
1. Open admin order ledger.
2. Locate an order.
3. View safe order/payment telemetry.
4. Apply an allowed status mutation.
5. Verify audit visibility.

### BW-104 — Coupons
1. Create/update/activate a coupon.
2. Apply it from a customer checkout session.
3. Verify the customer result matches the admin configuration.

### BW-105 — Shipping/fulfillment
1. Open shipping methods/fulfillment.
2. Verify configured methods and rates.
3. Create or manage shipment for an eligible order.
4. Verify AWB/pickup/label/tracking state when provider-backed.

### BW-106 — Settings/RBAC
1. Open settings/RBAC.
2. Read effective configuration.
3. Change one permitted setting with required reason/context.
4. Verify audit record.
5. Change a role/permission where authorized.
6. Verify affected action boundary.
7. Verify unauthorized/self-escalation attempts fail.

## 9. Security/browser-hardening workflows

### BW-120 — Protected-route access
Directly navigate to protected routes while signed out.
Expected: deterministic redirect/denial; no sensitive UI bootstrap data.

### BW-121 — Cross-user isolation
Use two test accounts.
Create data as A.
Attempt to access it as B.
Expected: server-side denial/not-found according to contract.

### BW-122 — Duplicate-submit safety
Double-click critical mutations such as checkout, payment confirmation, coupon redemption and admin writes.
Expected: backend idempotency/transaction policy prevents duplicate business effects.

### BW-123 — Error recovery
For every major workflow, verify:
- loading;
- success;
- validation failure;
- 401;
- 403;
- 404;
- 409/concurrency where relevant;
- 5xx/provider failure.

## 10. Release browser gate

The release browser gate should execute at minimum:

```text
BW-001
  -> BW-002
  -> BW-003
  -> BW-011
  -> BW-020
  -> BW-030
  -> BW-031
  -> BW-050
  -> BW-100
```

Add provider-specific BW-040/BW-041 and fulfillment flows when those live integrations are enabled.

## 11. Test-data policy

Browser tests must use dedicated test identities/data.
Never use:
- real customer passwords;
- production card data;
- production service-role credentials;
- destructive real-customer order mutations.

Use deterministic fixtures and unique identifiers for every run where possible.

## 12. Definition of done

A feature is browser-complete only when:

```text
UI implemented
  + API contract verified
  + auth/permission boundary verified
  + persistence/provider result verified
  + loading/success/error states verified
  + browser workflow documented
  + browser test automated where practical
  + CI/release evidence recorded
= complete
```
