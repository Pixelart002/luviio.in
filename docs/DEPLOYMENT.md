# Production Deployment Guide

## Dependency source

`pyproject.toml` defines the project requirements and `uv.lock` is the authoritative resolved dependency graph. Do not introduce `requirements.txt`, Pipenv, Poetry, or another package-manager lockfile.

Production installs must use the lockfile without changing dependency resolution:

```text
uv lock --check
uv sync --locked --no-dev --no-editable
python -m compileall -q app
pytest -q
```

## Build and runtime

The application entrypoint is `app.main:app`. The production process must run the ASGI application through the deployment platform's supported command/Procfile. Production configuration is supplied through environment variables; local `.env` files and credentials are never committed.

The Docker image uses Python 3.13 and uv. Dependency installation must remain lockfile-driven; image builds must not silently resolve a new dependency graph.

## Required production configuration

Configure the environment-specific Supabase, Stripe, webhook, email, push, CORS, and observability settings required by the deployed features. Server-only credentials must remain in the platform's secret manager/environment configuration.

## Release checklist

1. Review the complete diff for secrets, credentials, generated files, and accidental debug code.
2. Confirm the committed `uv.lock` matches `pyproject.toml`.
3. Run locked dependency installation and the compile, lint, type-check, dependency-audit, and test gates used by CI.
4. Apply reviewed database migrations before enabling code that depends on them.
5. Confirm webhook endpoints, signing secrets, CORS origins, and external-provider configuration match the target environment.
6. Deploy and verify `/health`, critical API flows, structured logs, and error monitoring.
7. Monitor the release before treating it as complete.

## Rollback

Rollback application code through the deployment platform's release mechanism. Roll back database changes only through a reviewed corrective migration or an explicitly documented recovery procedure. Do not use runtime settings as a substitute for a code or database rollback.

## Operational safety

Run scheduled jobs only through the configured scheduler/worker mechanism. Jobs must be idempotent and safe under retries. Do not assume process-local memory is shared between instances.
