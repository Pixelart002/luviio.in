# LUVIIO Order → Manual Fulfillment → Delivery Workflow

## Customer lifecycle

1. Customer signs in and adds products to cart.
2. Backend calculates product GST and the canonical manual-shipping policy.
3. Checkout creates the order/payment attempt.
4. Stripe confirmation or COD creation moves the order into the authoritative order state machine.
5. Customer receives the order confirmation.
6. Admin sees the order in the Orders panel.
7. Admin creates the internal manual shipment record when the order is ready for dispatch.
8. Staff chooses the actual courier/local delivery service outside Luviio and manually records tracking details when available.
9. Staff updates shipment/order status as the parcel moves.
10. Once dispatched, the order becomes shipped.
11. Delivery confirmation changes the order to delivered.
12. Customer sees the manual shipment/tracking information in Order Details.

## Shipping pricing

Checkout uses:
- ₹45.90 shipping below ₹1,499 subtotal.
- Free shipping at ₹1,499 or above.

The same canonical pricing configuration is used by Stripe and COD checkout. No external courier rate is queried.

## Shipment state

The internal shipment record uses manual fulfillment metadata. External courier-specific lifecycle operations such as AWB assignment, pickup scheduling, label generation, manifest generation and provider webhooks are disabled.

## Customer API

GET /api/v1/shipping/my/{order_number} returns only the authenticated customer's shipment record.

## Admin API

- GET /api/v1/shipping/provider/shipments
- POST /api/v1/shipping/provider/orders/{order_id}
- POST /api/v1/shipping/provider/shipments/{shipment_id}/cancel
- GET /api/v1/shipping/provider/track/{tracking_number}

The existing shipping route namespace is retained for API compatibility, but the shipping mode is always manual.

## Production configuration

No external courier-provider credentials are required for shipping. The backend defaults to:

SHIPPING_PROVIDER=manual
