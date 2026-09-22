# Contributing

## Add a feature

1. Identify the owning domain and public API contract.
2. Add or update the domain router and DTOs.
3. Put business rules in the domain service.
4. Put database access behind the domain repository.
5. Add authentication, authorization, validation, and ownership checks where required.
6. Add tests for success, invalid input, unauthorized/forbidden access, and important failure paths.
7. Update the affected architecture or operational documentation.

## Quality bar

Keep functions small, types explicit, and names descriptive. Prefer composition over duplicate services. Use the canonical `app/domains` architecture. Do not add deprecated framework APIs, a second package manager, raw SQL built from user input, secrets in source/logs, or process-local state for correctness-critical behavior.

## Dependencies

`pyproject.toml` is the dependency declaration and `uv.lock` is the committed resolution. Dependency changes must update the lockfile and pass the locked CI install. Do not add `requirements.txt` or another package-manager lockfile.

## Before opening a pull request

Run:

```bash
uv lock --check
uv sync --locked --dev
uv run python -m compileall -q app
uv run ruff check app tests
uv run mypy app --config-file mypy.ini
uv run pip-audit --strict
uv run pytest -q
```

Do not merge a production change with a failing CI verification gate.
