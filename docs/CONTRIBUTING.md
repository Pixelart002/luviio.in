# Contributing

## Add a feature

1. Identify the API route and DTO.
2. Add a small service for business rules.
3. Add or update a repository for database access.
4. Add authorization and validation.
5. Add tests for success, invalid input and forbidden access.
6. Update architecture or operational docs.

## Quality bar

Keep functions small, types explicit and names descriptive. Prefer composition over duplicate services. Do not add deprecated framework APIs, a second package manager, raw SQL built from user input, or secrets in source/logs.

## Before opening a pull request

Run `uv lock --check`, `uv sync --locked --no-dev --no-editable`, `python -m compileall -q app`, and `pytest`.
