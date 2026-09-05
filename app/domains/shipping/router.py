"""
Shipping Domain — Router
=========================
Path: app/domains/shipping/router.py

  * Public  -> GET  /shipping/methods    (active methods for checkout)
  * Public  -> POST /shipping/rate       (compute shipping for a cart)
  * Admin   -> CRUD /shipping/manage/...
"""
import logging

from fastapi import APIRouter, Depends, status

from app.core.dependencies import require_permission
from app.domains.shipping.service import ShippingService
from app.domains.shipping.schemas import (
    ShippingMethodCreate, ShippingMethodUpdate, ShippingRateRequest,
)
from app.permissions.shipping import ShippingPermissions
from app.constants.shipping_messages import ShippingMessages
from app.utils.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipping", tags=["Shipping"])

_service = ShippingService()


# ── Public ─────────────────────────────────────────────────────────────────────
@router.get("/methods", status_code=status.HTTP_200_OK,
            dependencies=[Depends(require_permission(ShippingPermissions.READ))])
async def list_methods(active_only: bool = True):
    data = await _service.list_methods(active_only)
    return success_response(data={"items": data}, message=ShippingMessages.METHODS_FETCHED)


@router.post("/rate", status_code=status.HTTP_200_OK,
             dependencies=[Depends(require_permission(ShippingPermissions.READ))])
async def compute_rate(payload: ShippingRateRequest):
    data = await _service.compute_rate(
        subtotal=payload.cart_subtotal,
        item_count=payload.item_count,
        weight_kg=payload.total_weight_kg,
        method_id=payload.method_id,
        pincode=payload.pincode,
    )
    return success_response(data=data, message=ShippingMessages.RATE_COMPUTED)


# ── Admin ──────────────────────────────────────────────────────────────────────
@router.post("/manage", status_code=201,
             dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def create_method(payload: ShippingMethodCreate):
    data = await _service.create(payload.model_dump())
    return success_response(data=data, message=ShippingMessages.METHOD_CREATED)


@router.patch("/manage/{method_id}", status_code=200,
              dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def update_method(method_id: str, payload: ShippingMethodUpdate):
    data = await _service.update(method_id, payload.model_dump(exclude_unset=True))
    return success_response(data=data, message=ShippingMessages.METHOD_UPDATED)


@router.delete("/manage/{method_id}", status_code=200,
               dependencies=[Depends(require_permission(ShippingPermissions.DELETE))])
async def delete_method(method_id: str):
    await _service.delete(method_id)
    return success_response(data={"method_id": method_id}, message=ShippingMessages.METHOD_DELETED)
