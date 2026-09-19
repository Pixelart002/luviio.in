# LUVIIO Order → Fulfillment → Delivery Workflow

## Customer lifecycle

1. Customer signs in and adds products to cart.
2. Backend calculates stock, product GST, shipping and final total.
3. Checkout creates the order/payment attempt.
4. Stripe confirmation or COD creation moves the order into the authoritative order state machine.
5. Customer receives order confirmation/payment notification.
6. Admin sees the order in the Orders panel.
7. Admin opens Shipping → Courier fulfillment.
8. Admin creates the provider shipment using the final package weight and dimensions.
9. LUVIIO assigns a courier/AWB through the provider.
10. LUVIIO schedules pickup.
11. LUVIIO generates label, manifest and provider invoice artifacts.
12. Provider webhook or scheduled tracking synchronization updates shipment status.
13. Once the courier has actually picked up/dispatched the package, the order becomes `shipped`.
14. `out_for_delivery` remains a shipment/provider status while the customer order remains `shipped`.
15. Provider `delivered` changes the order to `delivered`.
16. Customer sees courier, AWB and a shipment timeline in Order Details.
17. Post-delivery jobs send a review follow-up after ~24h and a support/care follow-up after ~72h. Follow-up send markers are persisted in shipment metadata to avoid repeat sends.

## Shipment state

`created -> awb_assigned -> pickup_scheduled -> picked_up -> in_transit -> out_for_delivery -> delivered`
Failure/exception states include `cancelled` and provider-specific RTO states.

## Order vs shipment state

Order status is intentionally coarse:
`pending -> paid -> processing -> shipped -> delivered`
The courier shipment has the granular operational status. This prevents provider-specific statuses from corrupting the order/payment state machine.

## Provider API lifecycle

Shiprocket's documented external API lifecycle includes order creation, courier/AWB assignment, pickup generation, manifest generation, label generation, invoice generation and AWB tracking. LUVIIO now has provider-neutral boundaries for these operations.

## Webhooks

`POST /api/v1/shipping/provider/webhook/{provider}` accepts provider shipment events only with the configured `LUVIIO_SHIPPING_WEBHOOK_SECRET` header. Provider event IDs are persisted in `shipping_shipment_events` for idempotent processing.

## Customer API

`GET /api/v1/shipping/my/{order_number}` returns only the authenticated customer's shipment record.

## Admin API

- `GET /api/v1/shipping/provider/shipments`
- `POST /api/v1/shipping/provider/orders/{order_id}`
- `POST /api/v1/shipping/provider/shipments/{shipment_id}/awb`
- `POST /api/v1/shipping/provider/shipments/{shipment_id}/pickup`
- `POST /api/v1/shipping/provider/shipments/{shipment_id}/label`
- `POST /api/v1/shipping/provider/shipments/{shipment_id}/manifest`
- `POST /api/v1/shipping/provider/shipments/{shipment_id}/invoice`
- `POST /api/v1/shipping/provider/shipments/{shipment_id}/sync`
- `POST /api/v1/shipping/provider/shipments/{shipment_id}/cancel`
All admin mutation endpoints remain permission protected.

## Required production configuration

- `SHIPROCKET_EMAIL`
- `SHIPROCKET_PASSWORD`
- `LUVIIO_SHIPPING_WEBHOOK_SECRET`
- `RESEND_API_KEY`
- `RESEND_FROM`
- `PUBLIC_APP_URL`
The pickup location must be configured/selected by the operator and must correspond to a valid provider pickup address.

## Important package data

Product weight is not the same as final package weight. Courier booking uses the final packed shipment's actual weight and dimensions. The admin fulfillment workflow therefore asks for final package weight and L/B/H before creating the courier shipment.