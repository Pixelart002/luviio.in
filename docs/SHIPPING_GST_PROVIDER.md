# Shipping + GST + Manual Fulfillment

## GST treatment

Luviio treats charged shipping/freight as part of the taxable checkout value when it is incidental/ancillary to the goods supply.

- Shipping below the free-shipping threshold is charged by the store shipping policy.
- Charged shipping is allocated across cart lines by taxable line value.
- Each allocated freight portion uses that line's GST rate.
- Shipping GST is included in the order tax snapshot.
- Free shipping has zero shipping taxable value and zero shipping GST.

## Manual shipping SSOT

Production checkout uses Luviio-owned manual shipping settings:

- shipping_enabled = true
- flat_shipping_rate = 45.90 INR
- free_shipping_threshold = 1499 INR
- shipping provider/mode = manual

No external courier API is called for checkout rates, serviceability, shipment creation, pickup, labels, manifests, or tracking synchronization.

## Fulfillment

Orders are persisted with shipping_provider = manual. Admin staff can create and update the internal shipment record and manually enter courier/tracking details when the parcel is actually handed to a courier or local delivery service.

## Customer tracking

GET /api/v1/shipping/my/{order_number} returns the authenticated customer's manual shipment record.

## Admin APIs

The existing /api/v1/shipping/provider/* routes are retained as stable internal fulfillment boundaries. External courier operations are disabled; staff update the shipment record manually.

## Environment

The production environment does not require external courier-provider credentials for shipping.
