# Luviio ecommerce workflow

## Product API

Products use `price` and `compare_price` as INR decimal values. Shipping data is explicit: `package.weight`, `package.weight_unit`, and `package.dimensions` with `length`, `width`, `height`, and `unit`. The API derives actual, volumetric, and chargeable weight rather than reading free-form `Weight` or `Dimensions` strings.

`sku` identifies inventory, `slug` identifies public lookup, `hsn_code` and `gst_percentage` identify tax, and `images` is the canonical ordered image list. Product price, stock, GST, and package metadata are persisted in the database; discount and chargeable-weight summaries are derived at runtime.

## Checkout and shipping

1. Read cart and product rows from the database.
2. Recompute price, GST, discount, stock, package weight, and chargeable volumetric weight on the server.
3. Check destination serviceability and calculate rates using Decimal arithmetic.
4. Snapshot email, address, prices, tax, shipping, and package data into the order.
5. Create an idempotent payment intent.
6. Confirm payment through Stripe/webhook verification.
7. Settle the order and stock reservation transactionally.
8. Create a Shiprocket shipment only after the order is paid and the snapshot is immutable.
9. Persist Shiprocket order/AWB/tracking IDs and accept signed provider status webhooks.

## Shiprocket states

`created -> serviceable -> order_created -> awb_assigned -> pickup_scheduled -> picked_up -> in_transit -> out_for_delivery -> delivered`.

Terminal states are `delivered`, `cancelled`, `rto`, and `failed`. Provider status strings must be mapped into this finite state machine; unknown statuses are retained as raw provider data and do not mutate the canonical state.

## Lookup ownership

Database lookups are required for stock, coupons, authorization, orders, addresses, and idempotency. Stripe is authoritative for payment status and amount. Shiprocket is authoritative for carrier serviceability, AWB, label, and tracking. Public catalog data may be cached, but checkout and fulfilment data must be fresh.

## Configuration

Set `SHIPROCKET_EMAIL`, `SHIPROCKET_PASSWORD`, and optionally `SHIPROCKET_BASE_URL` only on the backend. Never send provider credentials to the browser. If credentials are absent, the database shipping methods remain available and live Shiprocket serviceability is not attempted.
