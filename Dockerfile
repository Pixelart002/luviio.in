FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/
COPY pyproject.toml ./
RUN uv lock && uv sync --no-dev --no-install-project
COPY app ./app
EXPOSE 8000
CMD ["sh", "-c", "exec uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
