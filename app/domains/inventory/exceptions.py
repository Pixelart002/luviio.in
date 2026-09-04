"""
Inventory Exceptions
====================
Path: app/domains/inventory/exceptions.py

Domain-specific exceptions for inventory operations.
"""
from fastapi import HTTPException, status


class InsufficientStockError(HTTPException):
    """Raised when attempting to reserve more stock than available."""
    def __init__(self, product_id: str, requested: int, available: int):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Insufficient stock for product {product_id}. Requested: {requested}, Available: {available}"
        )


class ReservationFailedError(HTTPException):
    """Raised when stock reservation fails."""
    def __init__(self, order_id: str, reason: str = "Unknown"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stock reservation failed for order {order_id}. Reason: {reason}"
        )


class StockReleaseFailedError(HTTPException):
    """Raised when releasing reserved stock fails."""
    def __init__(self, order_id: str, reason: str = "Unknown"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to release stock for order {order_id}. Reason: {reason}"
        )


class ProductNotFoundError(HTTPException):
    """Raised when product does not exist."""
    def __init__(self, product_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found"
        )
