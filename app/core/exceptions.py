import logging
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError as PostgrestError
from app.utils.response import error_response
from app.constants.messages import ErrorMessages

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  DOMAIN EXCEPTIONS (Business Logic Errors)
# ══════════════════════════════════════════════════════════════════════════════

class LuviioException(Exception):
    """Base exception for all domain-specific errors."""
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

class ProductNotFound(LuviioException):
    def __init__(self, item_id: str):
        super().__init__(f"Product '{item_id}' not found.", "PRODUCT_NOT_FOUND", status.HTTP_404_NOT_FOUND)

class OutOfStockException(LuviioException):
    def __init__(self, item_name: str):
        super().__init__(f"Item '{item_name}' is currently out of stock.", "OUT_OF_STOCK", status.HTTP_409_CONFLICT)

class PaymentFailedException(LuviioException):
    def __init__(self, reason: str):
        super().__init__(f"Payment processing failed: {reason}", "PAYMENT_FAILED", status.HTTP_402_PAYMENT_REQUIRED)

class InvalidCouponException(LuviioException):
    def __init__(self, code: str):
        super().__init__(f"Coupon code '{code}' is invalid or expired.", "INVALID_COUPON", status.HTTP_400_BAD_REQUEST)

class ResourceNotFound(LuviioException):
    def __init__(self, resource_name: str):
        super().__init__(f"{resource_name} not found.", "RESOURCE_NOT_FOUND", status.HTTP_404_NOT_FOUND)


# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL EXCEPTION HANDLERS (Mounted in main.py)
# ══════════════════════════════════════════════════════════════════════════════

def register_exception_handlers(app):
    
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
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response(code="DB_ERROR", message="Database operation failed", details={"pg_code": exc.code}),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled Exception | path=%s | error=%s", request.url.path, str(exc), exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(code="INTERNAL_SERVER_ERROR", message=ErrorMessages.INTERNAL_ERROR),
        )