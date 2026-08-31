# Settings and Runtime Controls

## Who should use it?

- **Super admin:** system-locked and high-impact controls.
- **Admin:** operational and feature settings.
- **Manager:** only the settings explicitly granted by policy.
- **Developer:** adds typed keys and connects them to a real consumer.
- **Customer:** never gets direct settings API access.

## Setting contract

Each `system_settings` row should have a stable key, category, data type, current value, default value, description, lock flag and public flag. Keys are configuration, not business records.

Recommended operational keys:

| Key | Type | Default | Consumer |
|---|---|---:|---|
| `maintenance_mode` | boolean | `false` | `app/core/maintenance.py` |
| `enable_cod` | boolean | `true` | checkout/payment service |
| `enable_online_payment` | boolean | `true` | payment service |
| `tax_percentage` | number | `0` | order pricing service |
| `shipping_charge` | number | `0` | order pricing service |
| `minimum_order_value` | number | `0` | cart/order validation |
| `max_cart_items` | integer | `50` | cart validation |
| `enable_push_notifications` | boolean | `false` | push service |

## API usage

All settings endpoints require the existing admin authorization dependency. The exact response envelope remains the one defined by the router.

```http
GET /api/v1/settings/
PATCH /api/v1/settings/{key}
POST /api/v1/settings/{key}/reset
```

Update payload example:

```json
{"value": true, "reason": "Planned maintenance"}
```

## What not to store here

Do not store passwords, API keys, payment credentials, user preferences, permissions, product data or rapidly changing counters. Use environment secrets, user tables, RBAC policy, product tables or a purpose-built counter respectively.

## Safe rollout

1. Add the key and default.
2. Add validation and a single named consumer.
3. Add tests for default, enabled and malformed values.
4. Release with the default behavior unchanged.
5. Change the value through an authorized admin request.
6. Monitor logs and revert using the reset endpoint if needed.

`maintenance_mode=true` blocks business APIs with `503`; health, auth, settings and docs remain available. Never use maintenance mode as a replacement for deployment rollback, access control or incident response.
