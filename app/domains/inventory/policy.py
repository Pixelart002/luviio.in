"""
Inventory Policy
================
Path: app/domains/inventory/policy.py

Authorization rules for inventory operations.
"""
import logging
from typing import Optional
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class InventoryPolicy:
    """Permission checks for inventory operations."""

    # Permission constants (match existing permission pattern)
    VIEW_STOCK = "inventory:read"
    ADJUST_STOCK = "inventory:adjust"
    VIEW_LOW_STOCK = "inventory:low_stock:read"
    RELEASE_RESERVATION = "inventory:reservation:release"

    @staticmethod
    def assert_can_view_stock(user: dict) -> None:
        """Only admins/staff can view stock levels."""
        if user.get("role") not in ("admin", "staff"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to view stock levels"
            )

    @staticmethod
    def assert_can_adjust_stock(user: dict) -> None:
        """Only admins can manually adjust stock."""
        if user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to adjust stock"
            )

    @staticmethod
    def assert_can_release_reservation(user: dict) -> None:
        """Only admins/staff can manually release stock reservations."""
        if user.get("role") not in ("admin", "staff"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to release stock reservations"
            )

    @staticmethod
    def assert_can_view_low_stock(user: dict) -> None:
        """Only admins/staff can view low-stock alerts."""
        if user.get("role") not in ("admin", "staff"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to view low-stock alerts"
            )
