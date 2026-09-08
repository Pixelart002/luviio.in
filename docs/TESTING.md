# Testing

## Run locally

```bash
uv sync --dev
uv run pytest
```

## Test layout

- `test_app.py`: application and route contracts.
- `test_pricing.py`: GST, totals, money precision, and shipping.
- `test_payments.py`: provider composition and checkout validation.
- `test_settings.py`: settings facade and maintenance behavior.
- `test_health.py`: database health success path.
- `test_security.py`: response headers and unknown-route behavior.

## Rules

The test suite is self-contained and uses test-only environment placeholders. No Supabase, Stripe, Resend, push provider, Sentry, or scheduler credentials are required. Coverage is emitted as `coverage.xml`; CI enforces the configured minimum, plus Ruff, mypy, and dependency audit gates.

Tests must be deterministic and must not call Supabase, Stripe, Resend, push providers, or schedulers. Patch external boundaries and assert the application contract. Keep tests in Arrange/Act/Assert form and add a focused module when a new domain is introduced.
