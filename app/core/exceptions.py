"""
Global Exception Handlers
==========================
Architecture Layer: Core (Application Global)
Path: app/core/exceptions.py

Design:
  • Fail-Fast Principle: Catch all unhandled exceptions.
  • Security: Mask internal database/system errors from public view.
  • Observability: Log full stack trace for internal debugging.
"""
import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError as PostgrestError

logger = logging.getLogger(__name__)

class AppBaseException(Exception):
    """Base class for all custom domain exceptions"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code

def register_exception_handlers(app):
    """
    Register global exception handlers with the FastAPI app.
    Call this function in main.py.
    """

    @app.exception_handler(PostgrestError)
    async def postgrest_error_handler(request: Request, exc: PostgrestError):
        # Log the full error internally, but hide details from user
        logger.warning("Database error | code=%s | path=%s", exc.code, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Database operation failed", "code": exc.code},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # Log the full stack trace for internal debugging
        logger.error("Unhandled Exception | path=%s | error=%s", request.url.path, str(exc), exc_info=True)
        
        # Return a sanitized error to the client
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred. Please contact support."},
        )