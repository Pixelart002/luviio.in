"""
Order Router — Async Hardened Production Grade
==============================================
Path: app/domains/orders/router.py
"""
import io
import logging
from uuid import UUID
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.permissions.orders import OrderPermissions
from app.enums.roles import UserRole
from app.domains.orders.schemas import OrderAdminUpdate, OrderCancelResponse, OrderCreateFromCartRequest
from app.domains.orders.service import OrderService
from app.domains.payments.service import PaymentService
from app.constants.order_messages import OrderMessages
from app.utils.response import success_response
from app.utils.pagination import paginate


def _get_real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def create_order_from_cart(request: Request, payload: OrderCreateFromCartRequest, user_id: str = Depends(get_user_id_strict)):
    if not payload.idempotency_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="idempotency_key is required for checkout.")
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Checkout initiated by UID: {user_id[:8]}...")
    data = await PaymentService().create_intent(
        user_id=user_id,
        client_ip=_get_real_ip(request),
        idempotency_key=payload.idempotency_key,
        address_id=str(payload.shipping_address_id),
        user_agent=request.headers.get("user-agent", ""),
        coupon_code=payload.coupon_code,
    )
    return success_response(data=data, message="Order placed successfully.")


@router.get("/my", status_code=status.HTTP_200_OK)
async def my_orders(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status_filter: str = Query(None), user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"ABAC Scoped Fetch -> Target UID: {user_id[:8]}...")
    items, total = await OrderService().get_user_orders(user_id, status_filter, page, page_size)
    return paginate(items, total, page, page_size)


@router.get("/my/{order_id}", status_code=status.HTTP_200_OK)
async def get_my_order(request: Request, order_id: str, user_id: str = Depends(get_user_id_strict), current_user: Dict[str, Any] = Depends(get_current_user)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Targeting Order details for ID: {str(order_id)[:8]}...")
    is_admin = current_user.get("profile", {}).get("role") in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]
    return success_response(await OrderService().get_order(str(order_id), user_id, is_admin=is_admin))


@router.post("/my/{order_id}/cancel", status_code=status.HTTP_200_OK, response_model=OrderCancelResponse)
async def cancel_order(request: Request, order_id: UUID, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating Cancellation sequence for Order: {str(order_id)[:8]}...")
    return await OrderService().cancel_order(str(order_id), user_id)


@router.get("/", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(OrderPermissions.READ))])
async def list_all_orders(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status_filter: str = Query(None)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin fetching global order ledger (Page: {page})")
    items, total = await OrderService().get_all_orders(status_filter, page, page_size)
    return paginate(items, total, page, page_size)


@router.patch("/{order_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(OrderPermissions.UPDATE))])
async def admin_update_order(request: Request, order_id: UUID, payload: OrderAdminUpdate):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin overriding state for Order: {str(order_id)[:8]}...")
    result = await OrderService().admin_update_order(str(order_id), payload.model_dump(exclude_unset=True))
    return success_response(data=result, message=OrderMessages.UPDATE_SUCCESS)


@router.get("/{order_id}/invoice", status_code=status.HTTP_200_OK)
async def download_invoice(request: Request, order_id: UUID, current: dict = Depends(get_current_user), user_id: str = Depends(get_user_id_strict)):
    """Generate the order invoice from the owning Orders domain."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Targeting Invoice download for Order: {str(order_id)[:8]}...")
    role = current.get("profile", {}).get("role")
    is_admin = role in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, UserRole.MANAGER.value]
    pdf_bytes = await OrderService().generate_invoice_pdf(str(order_id), user_id, is_admin)
    filename = f"Luviio-Invoice-{str(order_id)[:8].upper()}.pdf"
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Prepared Streaming attachment: '{filename}'")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Content-Length": str(len(pdf_bytes)), "Cache-Control": "no-store"},
    )
