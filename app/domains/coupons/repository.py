"""
Coupons Domain — Repository
============================
Path: app/domains/coupons/repository.py
"""
import logging
from typing import Any, List, Optional

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class AsyncCouponRepository:
    async def get_by_code(self, code: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("coupons").select("*").eq("code", code).maybe_single().execute()
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:COUPONS] get_by_code failed: %s", exc)
            return None

    async def get_by_id(self, coupon_id: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("coupons").select("*").eq("id", coupon_id).maybe_single().execute()
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:COUPONS] get_by_id failed: %s", exc)
            return None

    async def list_all(self, page: int = 1, page_size: int = 50) -> tuple[List[dict[str, Any]], int]:
        sb = await get_async_admin_supabase()
        offset = (page - 1) * page_size
        try:
            res = await (
                sb.table("coupons").select("*", count="exact")
                .order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
            )
            return res.data or [], res.count or 0
        except Exception as exc:
            logger.error("[REPO:COUPONS] list_all failed: %s", exc)
            return [], 0

    async def create(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("coupons").insert(data).maybe_single().execute()
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:COUPONS] create failed: %s", exc)
            return None

    async def update(self, coupon_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("coupons").update(data).eq("id", coupon_id).maybe_single().execute()
            )
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:COUPONS] update failed: %s", exc)
            return None

    async def delete(self, coupon_id: str) -> bool:
        sb = await get_async_admin_supabase()
        try:
            await sb.table("coupons").delete().eq("id", coupon_id).execute()
            return True
        except Exception as exc:
            logger.error("[REPO:COUPONS] delete failed: %s", exc)
            return False

    async def redemptions_for_user(self, coupon_id: str, user_id: str) -> int:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("coupon_redemptions").select("id", count="exact")
                .eq("coupon_id", coupon_id).eq("user_id", user_id).execute()
            )
            return res.count or 0
        except Exception as exc:
            logger.error("[REPO:COUPONS] redemptions_for_user failed: %s", exc)
            return 0

    async def users_used_coupon(self, coupon_id: str) -> int:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("coupon_redemptions").select("id", count="exact")
                .eq("coupon_id", coupon_id).execute()
            )
            return res.count or 0
        except Exception as exc:
            logger.error("[REPO:COUPONS] users_used_coupon failed: %s", exc)
            return 0

    async def record_redemption(self, coupon_id: str, user_id: str, order_id: str, discount: float) -> bool:
        sb = await get_async_admin_supabase()
        try:
            # Idempotent: a redemption already logged for this (coupon, order)
            # means payment already settled — do NOT double-count usage.
            existing = (await sb.table("coupon_redemptions")
                        .select("id")
                        .eq("coupon_id", coupon_id)
                        .eq("order_id", order_id)
                        .limit(1)
                        .execute()).data
            if existing:
                return True

            # Increment used_count atomically + log the redemption row.
            await sb.rpc("consume_coupon", {
                "p_coupon_id": coupon_id,
                "p_user_id": user_id,
                "p_order_id": order_id,
            }).execute()
            await sb.table("coupon_redemptions").insert({
                "coupon_id": coupon_id, "user_id": user_id,
                "order_id": order_id, "discount": discount,
            }).execute()
            return True
        except Exception as exc:
            logger.error("[REPO:COUPONS] record_redemption failed: %s", exc)
            return False
