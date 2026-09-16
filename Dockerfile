FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/
COPY pyproject.toml ./
RUN uv lock && uv sync --no-dev --no-install-project

COPY app ./app

EXPOSE 8000

# Preload the application once, then fork 4 async workers. This keeps the
# required 4-worker deployment while avoiding four independent full imports
# of the application and its heavy dependencies during startup.
CMD ["sh", "-c", "exec uv run --no-dev gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers 4 --preload --access-logfile - --error-logfile - --timeout 120"]
