"""
Inventory Policy
================
Authorization rules for inventory operations.
"""
import logging

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class InventoryPolicy:
    """Permission checks for inventory operations."""

    VIEW_STOCK = "inventory:read"
    ADJUST_STOCK = "inventory:adjust"
    VIEW_LOW_STOCK = "inventory:low_stock:read"
    RELEASE_RESERVATION = "inventory:reservation:release"
    RECEIVE_STOCK = "inventory:receive"
    PROCESS_RETURN = "inventory:return"
    RECORD_DAMAGE = "inventory:damage"
    RECORD_WASTAGE = "inventory:wastage"
    RECONCILE_STOCK = "inventory:reconcile"
    VIEW_HISTORY = "inventory:history:read"

    @staticmethod
    def assert_can_view_stock(user: dict) -> None:
        if user.get("role") not in ("admin", "staff"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions to view stock levels")

    @staticmethod
    def assert_can_adjust_stock(user: dict) -> None:
        if user.get("role") != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions to adjust stock")

    @staticmethod
    def assert_can_release_reservation(user: dict) -> None:
        if user.get("role") not in ("admin", "staff"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions to release stock reservations")

    @staticmethod
    def assert_can_view_low_stock(user: dict) -> None:
        if user.get("role") not in ("admin", "staff"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions to view low-stock alerts")
