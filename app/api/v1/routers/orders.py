"""
Order Router — Async Hardened Production Grade
==============================================
Path: app/api/v1/routers/orders.py
"""
import logging
from uuid import UUID
from typing import Any, Dict
from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.permissions.orders import OrderPermissions
from app.enums.roles import UserRole
from app.api.schemas.order_dto import OrderAdminUpdate, OrderCancelResponse
from app.services.orders.service import OrderService
from app.utils.response import success_response
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["Orders"])

@router.get("/my", status_code=status.HTTP_200_OK)
async def my_orders(
    request: Request, 
    page: int = Query(1, ge=1), 
    page_size: int = Query(20, ge=1, le=100), 
    status_filter: str = Query(None), 
    user_id: str = Depends(get_user_id_strict)
):
    """Returns paginated ledger of orders belonging strictly to the authenticated user."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"ABAC Scoped Fetch -> Target UID: {user_id[:8]}...")
    
    items, total = await OrderService().get_user_orders(user_id, status_filter, page, page_size)
    return paginate(items, total, page, page_size)

@router.get("/my/{order_id}", status_code=status.HTTP_200_OK)
async def get_my_order(
    request: Request, 
    order_id: UUID, 
    user_id: str = Depends(get_user_id_strict),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Fetches details of a specific order after validating ABAC ownership rules."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Targeting Order details for ID: {str(order_id)[:8]}...")
        
    is_admin = current_user.get("profile", {}).get("role") in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]
    return success_response(await OrderService().get_order(str(order_id), user_id, is_admin=is_admin))

@router.post("/my/{order_id}/cancel", status_code=status.HTTP_200_OK, response_model=OrderCancelResponse)
async def cancel_order(
    request: Request, 
    order_id: UUID, 
    user_id: str = Depends(get_user_id_strict)
):
    """Cancels a pending or paid order and restores product inventory stock atomically."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Initiating Cancellation sequence for Order: {str(order_id)[:8]}...")
        
    return await OrderService().cancel_order(str(order_id), user_id)

@router.get(
    "/", 
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(OrderPermissions.READ))]
)
async def list_all_orders(
    request: Request, 
    page: int = Query(1, ge=1), 
    page_size: int = Query(20, ge=1, le=100), 
    status_filter: str = Query(None)
):
    """
    PBAC Guarded: Returns global paginated ledger of all system orders.
    Required Permission: order:read
    """
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin fetching global order ledger (Page: {page})")
        
    items, total = await OrderService().get_all_orders(status_filter, page, page_size)
    return paginate(items, total, page, page_size)

@router.patch(
    "/{order_id}", 
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(OrderPermissions.UPDATE))]
)
async def admin_update_order(
    request: Request, 
    order_id: UUID, 
    payload: OrderAdminUpdate
):
    """
    PBAC Guarded: Admin state machine override for order status, tracking, and notes.
    Required Permission: order:update
    """
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin overriding state for Order: {str(order_id)[:8]}...")
        
    return success_response(await OrderService().admin_update_order(str(order_id), payload.model_dump(exclude_unset=True)))

@router.get("/my/{order_id}/invoice", status_code=status.HTTP_200_OK)
async def download_invoice(
    order_id: UUID, 
    user_id: str = Depends(get_user_id_strict),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Generates and streams a PDF tax invoice for an eligible order."""
    is_admin = current_user.get("profile", {}).get("role") in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]
    pdf_bytes = await OrderService().generate_invoice_pdf(str(order_id), user_id, is_admin=is_admin)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice_{order_id}.pdf"'}
    )