"""
Cart Attribute-Based Access Control (ABAC) Policies
===================================================
Path: app/permissions/policies/cart_policies.py
"""
import logging
from typing import Dict, Any
from fastapi import HTTPException, status
from app.constants.cart_messages import CartSecurityMessages, CartRules

logger = logging.getLogger(__name__)

class CartPolicy:
    
    @staticmethod
    def assert_product_available(product: Dict[str, Any], requested_qty: int) -> None:
        """ABAC Guard: Verifies product exists, is active, and has sufficient physical stock."""
        name = product.get("name", "Product") if product else "Product"
        
        if not product or not product.get("is_active"):
            logger.warning(f"ABAC Block | Attempted to add inactive/missing product: {name}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=CartSecurityMessages.PRODUCT_UNAVAILABLE.format(name=name)
            )
            
        stock = product.get("stock", 0)
        if stock < requested_qty:
            logger.warning(f"ABAC Block | Insufficient stock for {name}. Requested: {requested_qty}, Available: {stock}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=CartSecurityMessages.OUT_OF_STOCK.format(stock=stock, name=name)
            )

    @staticmethod
    def assert_item_limit(new_qty: int) -> None:
        """ABAC Guard: Enforces maximum allowed quantity per line item to prevent integer overflow/abuse."""
        if new_qty > CartRules.MAX_QTY_PER_ITEM:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=CartSecurityMessages.LIMIT_EXCEEDED.format(limit=CartRules.MAX_QTY_PER_ITEM)
            )

    @staticmethod
    def assert_can_remind(cart: Dict[str, Any]) -> None:
        """ABAC Guard: Ensures abandoned cart exists and actually contains items before dispatching notifications."""
        if not cart:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CartSecurityMessages.CART_NOT_FOUND)
        
        if not cart.get("cart_items"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CartSecurityMessages.EMPTY_CART_REMINDER)