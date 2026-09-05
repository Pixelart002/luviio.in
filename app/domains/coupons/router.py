"""
Coupons Domain — Router
========================
Path: app/domains/coupons/router.py

  * Admin CRUD           -> /api/v1/coupons  (manage)
  * Customer apply       -> /api/v1/coupons/apply
"""
import logging

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.domains.coupons.service import CouponService
from app.domains.coupons.schemas import CouponCreate, CouponUpdate, CouponApplyRequest
from app.permissions.coupons import CouponPermissions
from app.constants.coupon_messages import CouponMessages
from app.utils.response import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coupons", tags=["Coupons"])

_service = CouponService()


# ── Admin ──────────────────────────────────────────────────────────────────────
@router.get("/manage", dependencies=[Depends(require_permission(CouponPermissions.READ))], status_code=200)
async def list_coupons(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    items, total = await _service.list_all(page, page_size)
    return success_response(data={"items": items, "total": total}, message=CouponMessages.FETCHED)


@router.post("/manage", dependencies=[Depends(require_permission(CouponPermissions.CREATE))], status_code=201)
async def create_coupon(payload: CouponCreate):
    result = await _service.create(payload.model_dump())
    return success_response(data=result, message=CouponMessages.CREATED)


@router.patch("/manage/{coupon_id}", dependencies=[Depends(require_permission(CouponPermissions.UPDATE))], status_code=200)
async def update_coupon(coupon_id: str, payload: CouponUpdate):
    result = await _service.update(coupon_id, payload.model_dump(exclude_unset=True))
    return success_response(data=result, message=CouponMessages.UPDATED)


@router.delete("/manage/{coupon_id}", dependencies=[Depends(require_permission(CouponPermissions.DELETE))], status_code=200)
async def delete_coupon(coupon_id: str):
    await _service.delete(coupon_id)
    return success_response(data={"coupon_id": coupon_id}, message=CouponMessages.DELETED)


# ── Customer ───────────────────────────────────────────────────────────────────
@router.post("/apply", status_code=200, dependencies=[Depends(require_permission(CouponPermissions.APPLY))])
async def apply_coupon(
    payload: CouponApplyRequest,
    user_id: str = Depends(get_user_id_strict),
):
    result = await _service.apply(payload.code, payload.cart_subtotal, user_id)
    return success_response(data=result, message=CouponMessages.APPLIED)
