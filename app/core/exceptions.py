"""
Global Exception Handlers
==========================
Path: app/core/exceptions.py
"""
import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError as PostgrestError

logger = logging.getLogger(__name__)

class AppBaseException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code

def register_exception_handlers(app):
    @app.exception_handler(PostgrestError)
    async def postgrest_error_handler(request: Request, exc: PostgrestError):
        logger.warning("Database error | code=%s | path=%s", exc.code, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Database operation failed", "code": exc.code},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled Exception | path=%s | error=%s", request.url.path, str(exc), exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred. Please contact support."},
        )