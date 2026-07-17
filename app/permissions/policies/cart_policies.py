"""
Cart Attribute-Based Access Control (ABAC) Policies
===================================================
Path: app/permissions/policies/cart_policies.py
"""
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from app.constants.cart_messages import CartSecurityMessages

logger = logging.getLogger(__name__)

class CartPolicy:
    """Enforces attribute-based rules on products and cart boundaries."""

    @staticmethod
    def assert_product_available(product: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        ABAC Guard: Verifies that the targeted product exists and is marked active.
        Raises HTTP 404 if the product is unavailable or hidden.
        """
        if not product or not product.get("is_active", False):
            logger.warning("ABAC Cart Block | Reason: Inactive or missing product targeted.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=CartSecurityMessages.PRODUCT_NOT_FOUND
            )
        return product

    @staticmethod
    def assert_stock_sufficient(product: Dict[str, Any], requested_qty: int, existing_qty: int = 0) -> None:
        """
        ABAC Guard: Validates real-time inventory against total requested quantity.
        Raises HTTP 400 if requested stock exceeds available inventory or boundary limits.
        """
        total_qty = existing_qty + requested_qty
        
        if total_qty > 100:
            logger.warning("ABAC Cart Block | Reason: Max unit boundary exceeded (%d units).", total_qty)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=CartSecurityMessages.MAX_QTY_EXCEEDED
            )
            
        available_stock = product.get("stock", 0)
        if available_stock < total_qty:
            logger.warning("ABAC Cart Block | Reason: Out of stock. Req: %d, Avail: %d", total_qty, available_stock)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=CartSecurityMessages.OUT_OF_STOCK
            )