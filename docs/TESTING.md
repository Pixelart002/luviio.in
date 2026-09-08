# Testing and Verification

## Local verification

Use the committed dependency graph for deterministic local verification:

```bash
uv sync --locked --dev
uv run python -m compileall -q app
uv run ruff check app tests
uv run mypy app --config-file mypy.ini
uv run pip-audit --strict
uv run pytest -q
```

## Test layout

- `test_app.py`: application and route contracts.
- `test_pricing.py`: GST, totals, money precision, and shipping.
- `test_payments.py`: provider composition and checkout validation.
- `test_settings.py`: settings facade and maintenance behavior.
- `test_health.py`: database health success path.
- `test_security.py`: response headers and unknown-route behavior.

Additional focused tests may be added by domain as behavior grows. Critical flows should cover success, invalid input, unauthorized/forbidden access, idempotency, and provider/database failure paths.

## Test isolation

The automated suite is self-contained and uses test-only environment placeholders. Tests must not call production Supabase, Stripe, Resend, push providers, Sentry, or schedulers. Patch external boundaries and assert the application contract.

## CI standard

CI is the authoritative merge/release verification path. The workflow installs dependencies, compiles the application, runs Ruff and mypy, audits dependencies, executes pytest with coverage, and stores the coverage artifact.

A production change is not considered verified until the relevant CI run is green. Test results from an earlier commit must not be presented as evidence for a later source state.
