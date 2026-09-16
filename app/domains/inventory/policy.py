"""Inventory authorization constants and role-oriented policy helpers."""

from fastapi import HTTPException, status


class InventoryPolicy:
    VIEW_STOCK = "inventory.read"
    ADJUST_STOCK = "inventory.adjust"
    VIEW_LOW_STOCK = "inventory.low_stock.read"
    RELEASE_RESERVATION = "inventory.reservation.release"
    RECEIVE_STOCK = "inventory.receive"
    PROCESS_RETURN = "inventory.return"
    RECORD_DAMAGE = "inventory.damage"
    RECORD_WASTAGE = "inventory.wastage"
    RECONCILE_STOCK = "inventory.reconcile"
    VIEW_HISTORY = "inventory.history.read"

    @staticmethod
    def assert_admin(user: dict) -> None:
        if user.get("role") not in ("admin", "super_admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin inventory permission required")
