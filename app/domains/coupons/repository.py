"""
Coupons Domain — Repository
============================
Path: app/domains/coupons/repository.py
"""
import logging
from typing import Any, List, Optional

from fastapi.encoders import jsonable_encoder

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class AsyncCouponRepository:
    async def get_by_code(self, code: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("coupons")
                .select("*")
                .eq("code", code)
                .limit(1)
                .execute()
            )
            return (res.data or [None])[0]
        except Exception as exc:
            logger.exception("[REPO:COUPONS] get_by_code failed")
            raise RuntimeError("Coupon lookup failed") from exc

    async def get_by_id(self, coupon_id: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("coupons")
                .select("*")
                .eq("id", coupon_id)
                .limit(1)
                .execute()
            )
            return (res.data or [None])[0]
        except Exception as exc:
            logger.exception("[REPO:COUPONS] get_by_id failed")
            raise RuntimeError("Coupon lookup failed") from exc

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
            logger.exception("[REPO:COUPONS] list_all failed")
            raise RuntimeError("Coupon list failed") from exc

    async def create(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            # Supabase/PostgREST's async request builder expects JSON-native values.
            # Pydantic keeps valid_from/valid_until as datetime objects, so encode
            # them before sending the request.
            encoded_data = jsonable_encoder(data)
            await sb.table("coupons").insert(encoded_data).execute()
            code = data.get("code")
            if not code:
                return None
            return await self.get_by_code(str(code))
        except Exception as exc:
            logger.exception("[REPO:COUPONS] create failed")
            raise RuntimeError("Coupon creation failed") from exc

    async def update(self, coupon_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            encoded_data = jsonable_encoder(data)
            await sb.table("coupons").update(encoded_data).eq("id", coupon_id).execute()
            return await self.get_by_id(coupon_id)
        except Exception as exc:
            logger.exception("[REPO:COUPONS] update failed")
            raise RuntimeError("Coupon update failed") from exc

    async def delete(self, coupon_id: str) -> bool:
        sb = await get_async_admin_supabase()
        try:
            await sb.table("coupons").delete().eq("id", coupon_id).execute()
            return True
        except Exception as exc:
            logger.exception("[REPO:COUPONS] delete failed")
            raise RuntimeError("Coupon deletion failed") from exc

    async def redemptions_for_user(self, coupon_id: str, user_id: str) -> int:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("coupon_redemptions").select("id", count="exact")
                .eq("coupon_id", coupon_id).eq("user_id", user_id).execute()
            )
            return res.count or 0
        except Exception as exc:
            logger.exception("[REPO:COUPONS] redemptions_for_user failed")
            raise RuntimeError("Coupon redemption lookup failed") from exc

    async def users_used_coupon(self, coupon_id: str) -> int:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("coupon_redemptions").select("id", count="exact")
                .eq("coupon_id", coupon_id).execute()
            )
            return res.count or 0
        except Exception as exc:
            logger.exception("[REPO:COUPONS] users_used_coupon failed")
            raise RuntimeError("Coupon redemption lookup failed") from exc

    async def record_redemption(self, coupon_id: str, user_id: str, order_id: str, discount: float) -> bool:
        """Record a redemption and increment usage atomically in Postgres."""
        sb = await get_async_admin_supabase()
        try:
            res = await sb.rpc("record_coupon_redemption", {
                "p_coupon_id": coupon_id,
                "p_user_id": user_id,
                "p_order_id": order_id,
                "p_discount": discount,
            }).execute()
            return bool(res.data)
        except Exception as exc:
            logger.exception("[REPO:COUPONS] record_redemption failed")
            raise RuntimeError("Coupon redemption failed") from exc
