# Backend Hardening Runbook

## Production verification

1. Confirm browser roles have no direct table privileges on `users`, `addresses`, `carts`, `cart_items`, or `orders`.
2. Confirm transactional outbox trigger functions are callable only by `service_role` and the database owner.
3. Confirm the six FK indexes exist:
   - `idx_addresses_user_id`
   - `idx_audit_logs_actor_user_id`
   - `idx_notification_dlq_user_id`
   - `idx_payment_ledger_payment_id`
   - `idx_product_reviews_user_id`
   - `idx_user_subscriptions_plan_id`
4. Smoke-test auth throttling with unique hashes, then reset the test state.

## CI release gate

Run, in order:

```text
uv lock
uv sync --dev
python -m compileall -q app
ruff check app tests
mypy app
pip-audit
pytest --cov=app --cov-report=xml
```

Do not lower the lint bar just to make CI green. Tests must execute on release candidates.

## Checkout integrity matrix

Test in non-production:

```text
same idempotency key twice
same payment intent twice
payment success after cancellation
insufficient stock concurrently
single-use coupon concurrently
coupon expiry cleanup
cart price tampering
order financial-field tampering
role/is_active tampering
```

## Release evidence

Record the Git commit SHA, migration names, green CI run, Supabase advisor result, deployment/runtime verification, and rollback path.

## Hard rules

- Service credentials stay server-side.
- Browser-provided roles and permissions are never trusted.
- Client totals are never trusted for settlement.
- Process-local memory is never the correctness source for payments, inventory, coupons, or security throttles.
- Issued invoice snapshots are immutable.
