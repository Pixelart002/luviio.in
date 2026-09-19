# Shipping + GST + Provider

## GST treatment

Luviio now treats charged shipping/freight as part of the taxable checkout value when it is incidental/ancillary to the goods supply.

- Shipping below the free-shipping threshold is charged by the shipping policy.
- Charged shipping is allocated across cart lines by taxable line value.
- Each allocated freight portion uses that line's GST rate.
- The resulting shipping GST is included in order tax_amount and separately snapshotted as shipping_tax_amount.
- Invoice snapshots contain shipping allocation lines using SAC 9965 and the applicable GST rate for each allocation.
- Free shipping has zero shipping taxable value and zero shipping GST.
- Intra-state/inter-state split remains controlled by the order place-of-supply GST context.

Primary Indian source: CBIC CGST Act, Section 15(2)(c), plus CBIC FAQ guidance on cartage/loading/transport as ancillary to the principal supply.

## Store settings

Current production SSOT:

- shipping_enabled = true
- flat_shipping_rate = 45.90
- free_shipping_threshold = 1499

## Provider

The backend now has a provider-neutral shipping boundary with Shiprocket as the first adapter.

Capabilities:

- courier/serviceability lookup
- shipment creation
- AWB/tracking lookup
- provider shipment persistence

Required server-side environment variables:

- SHIPROCKET_EMAIL
- SHIPROCKET_PASSWORD

No provider credential is accepted from the browser.

Shiprocket account setup requires an API user and pickup location. Configure the credentials in the backend deployment before using provider shipment creation.

## Admin API

- GET /api/v1/shipping/provider/serviceability
- POST /api/v1/shipping/provider/orders/{order_id}
- GET /api/v1/shipping/provider/track/{tracking_number}

Provider shipment records are stored in public.shipping_shipments and are blocked from direct client writes by RLS.

## Regulatory limitation

Ansvar Gateway was checked for India GST coverage before implementation. Its current corpus has no IN jurisdiction, so it cannot provide India-GST provisions directly. Indian GST treatment was therefore verified against CBIC primary sources rather than treating an unrelated Ansvar jurisdiction as authoritative.
