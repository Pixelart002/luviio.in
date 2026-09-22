# Settings and Runtime Controls

## Purpose

`system_settings` stores operational configuration that may be changed at runtime by authorized administrators. It is not a secrets store and it is not a replacement for business records, RBAC policy, or provider credentials.

## Access model

- **Super admin:** system-locked and high-impact controls according to policy.
- **Admin:** operational and feature settings permitted by policy.
- **Manager:** only explicitly granted settings.
- **Developer:** defines typed keys and connects them to a real consumer through reviewed code changes.
- **Customer:** no direct settings API access.

## Setting contract

Each setting must have a stable key, category, data type, current value, default value, description, lock semantics, and public/private visibility as defined by the database contract. Values are validated before persistence and consumers must use the typed value expected by the owning domain.

Representative operational controls include maintenance mode, checkout/payment feature flags, pricing/shipping configuration, cart limits, notification enablement, and other explicitly registered runtime controls. The code and database migration are authoritative for the exact key set and defaults.

## API

All settings endpoints require the existing server-side authorization policy:

```http
GET /api/v1/settings/
PATCH /api/v1/settings/{key}
POST /api/v1/settings/{key}/reset
```

Example update payload:

```json
{"value": true, "reason": "Planned maintenance"}
```

## What not to store here

Do not store passwords, API keys, Stripe credentials, service-role keys, VAPID private keys, user preferences, permissions, product data, or rapidly changing counters. Use deployment secret management, user/domain tables, RBAC policy, product tables, or purpose-built counters respectively.

## Safe rollout

1. Add the key, type, validation, and default through a reviewed change.
2. Connect it to one clearly owned consumer.
3. Add tests for default, valid update, reset, authorization, and malformed values.
4. Deploy with the existing default behavior preserved.
5. Change the value through an authorized admin operation.
6. Monitor structured logs and application behavior.
7. Reset or roll back through the appropriate operational mechanism if the setting causes unsafe behavior.

`maintenance_mode=true` blocks business APIs with `503` while the explicitly exempt operational endpoints remain available according to middleware policy. Maintenance mode is not a replacement for deployment rollback, access control, or incident response.
