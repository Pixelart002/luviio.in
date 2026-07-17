"""
Global Exceptions & Domain Errors (SSOT)
========================================
Path: app/core/exceptions.py
"""
import logging
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from postgrest.exceptions import APIError as PostgrestError
from app.utils.response import error_response
from app.constants.messages import ErrorMessages

logger = logging.getLogger(__name__)

class LuviioException(Exception):
    def __init__(
        self, 
        message: str = ErrorMessages.INTERNAL_ERROR, 
        code: str = "INTERNAL_ERROR", 
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR, 
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class UnauthorizedAction(LuviioException):
    def __init__(self, message: str = ErrorMessages.UNAUTHORIZED):
        super().__init__(message, "UNAUTHORIZED_ACTION", status.HTTP_403_FORBIDDEN)

class UnauthenticatedUser(LuviioException):
    def __init__(self, message: str = ErrorMessages.INVALID_TOKEN):
        super().__init__(message, "UNAUTHENTICATED", status.HTTP_401_UNAUTHORIZED)

class ResourceNotFound(LuviioException):
    def __init__(self, resource_name: str):
        super().__init__(f"{resource_name} not found.", "RESOURCE_NOT_FOUND", status.HTTP_404_NOT_FOUND)

def register_exception_handlers(app):
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(map(str, e["loc"])), "error": e["msg"]} for e in exc.errors()]
        logger.warning("Payload validation failed | path=%s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(code="VALIDATION_ERROR", message="Invalid request payload", details=errors)
        )

    @app.exception_handler(LuviioException)
    async def luviio_exception_handler(request: Request, exc: LuviioException):
        logger.warning("Domain Error | code=%s | path=%s | msg=%s", exc.code, request.url.path, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(code=exc.code, message=exc.message, details=exc.details),
        )

    @app.exception_handler(PostgrestError)
    async def postgrest_error_handler(request: Request, exc: PostgrestError):
        logger.error("Database Error | code=%s | path=%s | msg=%s", exc.code, request.url.path, exc.message)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=error_response(code="DB_ERROR", message="Database operation failed", details={"pg_code": exc.code}),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled Exception | path=%s | error=%s", request.url.path, str(exc), exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(code="INTERNAL_SERVER_ERROR", message=ErrorMessages.INTERNAL_ERROR),
        )