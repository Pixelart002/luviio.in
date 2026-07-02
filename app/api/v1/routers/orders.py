from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from app.core.dependencies import get_user_id_strict, require_permission
from app.permissions.orders import OrderPermissions
from app.api.schemas.order_dto import OrderAdminUpdate
from app.services.orders.service import OrderService
from app.utils.response import success_response
from app.utils.pagination import paginate

router = APIRouter(prefix="/orders", tags=["Orders"])

@router.get("/my")
async def my_orders(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status_filter: str = None, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"ABAC Scoped Fetch -> Target UID: {user_id[:8]}...")
    items, total = await OrderService().get_user_orders(user_id, status_filter, page, page_size)
    return paginate(items, total, page, page_size)

@router.get("/my/{order_id}")
async def get_my_order(request: Request, order_id: UUID, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Targeting Order details for ID: {str(order_id)[:8]}...")
    return success_response(await OrderService().get_order(str(order_id), user_id))

@router.post("/my/{order_id}/cancel")
async def cancel_order(request: Request, order_id: UUID, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Initiating Cancellation sequence for Order: {str(order_id)[:8]}...")
    return success_response(await OrderService().cancel_order(str(order_id), user_id))

@router.get("/", dependencies=[Depends(require_permission(OrderPermissions.READ))])
async def list_all_orders(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status_filter: str = None):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin fetching global order ledger (Page: {page})")
    items, total = await OrderService().get_all_orders(status_filter, page, page_size)
    return paginate(items, total, page, page_size)

@router.patch("/{order_id}", dependencies=[Depends(require_permission(OrderPermissions.UPDATE))])
async def admin_update_order(request: Request, order_id: UUID, payload: OrderAdminUpdate):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin overriding state for Order: {str(order_id)[:8]}...")
    return success_response(await OrderService().admin_update_order(str(order_id), payload.model_dump(exclude_unset=True)))