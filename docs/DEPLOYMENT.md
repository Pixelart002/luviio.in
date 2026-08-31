# Deployment Guide

## Build source

Use `pyproject.toml` and the committed `uv.lock` as the only dependency source. `requirements.txt` must not be reintroduced because the Python buildpack rejects multiple package-manager files.

## Commands

```text
uv lock --check
uv sync --locked --no-dev --no-editable
python -m compileall -q app
pytest
```

## Runtime

The Procfile must start `app.main:app`. Production configuration is supplied through environment variables; never commit local `.env` files.

## Release checklist

1. Review the diff for secrets and generated files.
2. Confirm Supabase, Stripe and webhook configuration exists for the target environment.
3. Run the verification commands above.
4. Deploy from a feature branch and inspect health plus structured logs.
5. Roll back through the deployment platform if behavior is unsafe; do not use a runtime setting as a substitute for rollback.
