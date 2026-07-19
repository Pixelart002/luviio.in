"""
Cart Router — Async Standardized Endpoints
==========================================
Path: app/api/v1/routers/cart.py
"""
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import get_user_id_strict, require_permission
from app.api.schemas.cart_dto import AddItemRequest, UpdateItemRequest, CartResponse, MessageResponse, AbandonedCartResponse, ReminderResponse
from app.services.cart.service import CartService
from app.permissions.admin import AdminPermissions
from app.constants.cart_messages import CartMessages
from app.utils.response import success_response

router = APIRouter(prefix="/cart", tags=["Cart"])

@router.get("", response_model=CartResponse)
async def get_cart(request: Request, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.extend([f"ABAC Scoped -> Target UID: {user_id[:8]}...", "Fetching active cart vault & computing SSOT pricing"])
    
    data = await CartService().get_cart(user_id)
    return success_response(data=data)

@router.post("/items", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def add_item(request: Request, payload: AddItemRequest, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Verifying stock & adding product {str(payload.product_id)[:8]}...")
    
    data = await CartService().add_item(user_id, str(payload.product_id), payload.quantity)
    return success_response(data=data, message=CartMessages.ITEM_ADDED)

@router.put("/items/{product_id}", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def update_item(request: Request, product_id: UUID, payload: UpdateItemRequest, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Targeting cart line item {str(product_id)[:8]}... -> Qty: {payload.quantity}")
    
    data = await CartService().update_item(user_id, str(product_id), payload.quantity)
    return success_response(data=data, message=CartMessages.ITEM_UPDATED)

@router.delete("/items/{product_id}", status_code=status.HTTP_200_OK, response_model=CartResponse)
async def remove_item(request: Request, product_id: UUID, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Excised product {str(product_id)[:8]}… from active cart ledger")
        
    data = await CartService().remove_item(user_id, str(product_id))
    return success_response(data=data, message=CartMessages.ITEM_REMOVED)

@router.delete("", status_code=status.HTTP_200_OK, response_model=MessageResponse)
async def clear_cart(request: Request, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Purging all line items -> Active Cart reset to zero")
        
    await CartService().clear_cart(user_id)
    return success_response(message=CartMessages.CART_CLEARED)

@router.get("/admin/abandoned", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], response_model=AbandonedCartResponse)
async def list_abandoned_carts(request: Request, hours: int = Query(24, ge=1, le=168), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin sweeping abandoned carts (Threshold: >{hours}h)")
        
    data = await CartService().get_abandoned_carts(hours, page, page_size)
    return success_response(data=data)

@router.post("/admin/remind/{cart_id}", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))], response_model=ReminderResponse)
async def send_cart_reminder(request: Request, cart_id: UUID):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Triggering abandoned Cart reminder: {str(cart_id)[:8]}…")
        
    data = await CartService().send_cart_reminder(str(cart_id))
    return success_response(data=data, message=CartMessages.REMINDER_SENT)