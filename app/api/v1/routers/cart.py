"""
Cart Router — Async Hardened Production Grade
=============================================
Path: app/api/v1/routers/cart.py
"""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import get_user_id_strict, require_permission
from app.api.schemas.cart_dto import (
    AddItemRequest, UpdateItemRequest, CartResponse, 
    MessageResponse, AbandonedCartResponse, ReminderResponse
)
from app.services.cart.service import CartService
from app.permissions.admin import AdminPermissions
from app.constants.cart_messages import CartMessages

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cart", tags=["Cart"])

@router.get("", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def get_cart(request: Request, user_id: str = Depends(get_user_id_strict)):
    """Returns current active user cart with SSOT calculated pricing breakdown."""
    if hasattr(request.state, "actions"):
        request.state.actions.extend([f"ABAC Scoped -> Target UID: {user_id[:8]}...", "Fetching active cart vault & computing SSOT pricing"])
    
    return await CartService().get_cart(user_id)

@router.post("/items", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def add_item(request: Request, payload: AddItemRequest, user_id: str = Depends(get_user_id_strict)):
    """
    Adds item to cart. Enforces ABAC stock limits and active catalog state.
    """
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Verifying stock & adding product {str(payload.product_id)[:8]}...")
    
    result = await CartService().add_item(user_id, str(payload.product_id), payload.quantity)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(CartMessages.ITEM_ADDED)
    return result

@router.put("/items/{product_id}", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def update_item(request: Request, product_id: UUID, payload: UpdateItemRequest, user_id: str = Depends(get_user_id_strict)):
    """Updates line item quantity after running ABAC stock validation rules."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Targeting cart line item {str(product_id)[:8]}... -> Qty: {payload.quantity}")
    
    result = await CartService().update_item(user_id, str(product_id), payload.quantity)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(CartMessages.ITEM_UPDATED)
    return result

@router.delete("/items/{product_id}", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def remove_item(request: Request, product_id: UUID, user_id: str = Depends(get_user_id_strict)):
    """Removes a product line item entirely from active cart ledger."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Excised product {str(product_id)[:8]}… from active cart ledger")
        
    return await CartService().remove_item(user_id, str(product_id))

@router.delete("", status_code=status.HTTP_200_OK, response_model=MessageResponse)
async def clear_cart(request: Request, user_id: str = Depends(get_user_id_strict)):
    """Purges all line items from the user's cart."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Purging all line items -> Active Cart reset to zero")
        
    await CartService().clear_cart(user_id)
    return {"message": CartMessages.CART_CLEARED}

@router.get(
    "/admin/abandoned", 
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], 
    response_model=AbandonedCartResponse
)
async def list_abandoned_carts(
    request: Request, 
    hours: int = Query(24, ge=1, le=168), 
    page: int = Query(1, ge=1), 
    page_size: int = Query(20, ge=1, le=100)
):
    """
    PBAC Guarded: Lists all carts abandoned past the specified hour threshold.
    Required Permission: admin:view_analytics
    """
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin sweeping abandoned carts (Threshold: >{hours}h)")
        
    return await CartService().get_abandoned_carts(hours, page, page_size)

@router.post(
    "/admin/remind/{cart_id}", 
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))], 
    response_model=ReminderResponse
)
async def send_cart_reminder(request: Request, cart_id: UUID):
    """
    PBAC Guarded: Dispatches web push and email reminders for an abandoned cart.
    Required Permission: admin:manage_settings
    """
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Triggering abandoned Cart reminder: {str(cart_id)[:8]}…")
        
    result = await CartService().send_cart_reminder(str(cart_id))
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(CartMessages.REMINDER_SENT)
    return result