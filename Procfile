web: gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers 4 --preload --access-logfile - --error-logfile - --timeout 120
