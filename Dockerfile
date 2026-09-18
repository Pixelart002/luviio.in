FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/
COPY pyproject.toml ./
RUN uv lock && uv sync --no-dev --no-install-project

COPY app ./app

EXPOSE 8000

# Keep the web process memory-bounded. WEB_CONCURRENCY can be increased on a
# larger instance without changing the image; default is intentionally 2.
CMD ["sh", "-c", "exec uv run --no-dev gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --preload --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile - --timeout 120"]
