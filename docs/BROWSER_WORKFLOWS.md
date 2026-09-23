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

### BW-020 — Add/update/remove cart
1. Add product A.
2. Open `/cart`.
3. Verify server-confirmed quantity and total.
4. Update quantity.
5. Verify cart total changes from the API result.
6. Remove item.
7. Verify empty-cart state.

### BW-021 — Cart authorization
1. Open `/cart` while signed out.
2. Verify sign-in/recovery UX.
3. Sign in.
4. Verify the user's own cart appears.
5. Verify no other user's cart data is exposed.

## 4. Checkout workflows

### BW-030 — Checkout prerequisites
1. Add product to cart.
2. Sign in.
3. Open `/checkout`.
4. Verify saved addresses or deliberate empty-address state.
5. Select an address.
6. Verify checkout controls become actionable only when prerequisites are valid.

### BW-031 — Online checkout
1. Start from a non-empty cart.
2. Select shipping address.
3. Submit online checkout with a unique idempotency key.
4. Verify server-confirmed order result.
5. Verify cart is cleared only after successful order completion.
6. Verify confirmation contains public order identifier.

The browser must not calculate the authoritative subtotal, GST, shipping or final total.

### BW-032 — COD checkout
Same flow as BW-031 using COD.
Verify:
- COD method is available only when backend allows it;
- order is created once;
- repeated submission with the same idempotency key does not create a duplicate order.

### BW-033 — Checkout failure
Inject/trigger a deterministic backend rejection (invalid address, unavailable stock, disabled method, provider failure, etc.).
Verify:
- no false success;
- user receives actionable error;
- cart/order state remains consistent;
- retry does not duplicate an order.

## 5. Payment workflows

### BW-040 — Payment success
Precondition: test payment provider configuration.
1. Complete online checkout.
2. Complete provider confirmation.
3. Return to the application.
4. Verify settled order state.

### BW-041 — Payment failure
1. Start online payment.
2. Force a provider/client failure.
3. Verify failed/pending status is visible.
4. Verify no duplicate order/inventory mutation beyond backend policy.
5. Verify retry action when the order is retryable.

### BW-042 — Payment retry
1. Open a retryable pending order.
2. Start retry.
3. Verify retry attempt is represented.
4. Complete or fail the retry.
5. Verify UI reflects authoritative order/payment state.

### BW-043 — Payment method switch
1. Open an eligible pending order.
2. Switch payment method.
3. Verify server-confirmed method/state.
4. Complete the new method flow.

## 6. Order lifecycle workflows

### BW-050 — Order history
1. Sign in.
2. Open `/orders`.
3. Verify only the current user's orders.
4. Verify pagination/load-more behavior when applicable.

### BW-051 — Order detail
1. Select a known public order number.
2. Open `/orders/:orderNumber`.
3. Verify items, status, totals and customer-safe details.
4. Verify another user's order number cannot expose private order data.

### BW-052 — Invoice
1. Open an eligible order.
2. Trigger invoice view/download.
3. Verify the response is an invoice for that exact order.
4. Verify no internal/server-only fields are exposed.

### BW-053 — Order cancellation
1. Open an eligible order.
2. Cancel it.
3. Verify confirmed status.
4. Verify inventory/cart/payment side effects match backend policy.
5. Verify repeated cancellation is safely rejected or idempotent.

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
