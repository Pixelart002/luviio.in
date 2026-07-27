"""
Cart Repository — Async Enterprise Grade (GST & HSN Ready)
==========================================================
Path: app/repositories/cart_repo.py

Architecture & Fixes:
  ✅ Defensive Null Guards — Resolves IndexError risks during upserts and selects.
  ✅ Proper DB Error Handling — Logs exceptions cleanly without leaking internal traces or silent crashes.
  ✅ GST & HSN Ready — Explicitly fetches hsn_code and gst_percentage for downstream SSOT checkout.
  ✅ Automatic Cart Touching — Bumps carts.updated_at timestamp on line item mutations.
  ✅ Async ORM Compatible — Splitting upsert and read operations prevents query builder chaining errors.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Tuple, List, Optional
from fastapi import HTTPException, status
from app.core.supabase import get_async_admin_supabase
from app.constants.cart_messages import CartSecurityMessages

logger = logging.getLogger(__name__)

class AsyncCartRepository:
    def __init__(self):
        pass

    async def _touch_cart_timestamp(self, cart_id: str) -> None:
        """Bumps parent cart updated_at timestamp on every line item mutation."""
        try:
            admin_sb = await get_async_admin_supabase()
            now_iso = datetime.now(timezone.utc).isoformat()
            await admin_sb.table("carts").update({"updated_at": now_iso}).eq("id", cart_id).execute()
        except Exception as exc:
            logger.warning("Failed to touch cart timestamp for cart %s: %s", cart_id, exc)

    async def get_pricing_config(self) -> dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
            return res.data if res and getattr(res, "data", None) else {}
        except Exception as exc:
            logger.error("DB Error fetching pricing config: %s", exc, exc_info=True)
            return {}

    async def get_or_create_cart(self, user_id: str) -> dict[str, Any]:
        """
        Safely fetches or creates a user cart. Splitting upsert and select prevents 
        async query builder chaining exceptions.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            # Step 1: Perform the atomic upsert without chaining .select()
            await admin_sb.table("carts").upsert(
                {"user_id": user_id}, on_conflict="user_id"
            ).execute()
            
            # Step 2: Explicitly query for the record to ensure clean retrieval
            res = await admin_sb.table("carts").select("*").eq("user_id", user_id).limit(1).execute()
            
            data = getattr(res, "data", None)
            if data and len(data) > 0:
                return data[0]
                
            raise RuntimeError("Upsert succeeded but cart retrieval returned empty data.")
        except Exception as exc:
            logger.error("Critical DB failure in get_or_create_cart for UID %s: %s", user_id, exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=CartSecurityMessages.DB_OPERATION_FAILED
            ) from exc

    async def get_cart_items_with_products(self, cart_id: str) -> list[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("cart_items").select(
                "id, product_id, quantity, price_snapshot, added_at, "
                "products(id, name, slug, price, compare_price, stock, hsn_code, gst_percentage, image_url, is_active)"
            ).eq("cart_id", cart_id).order("added_at", desc=False).execute()
            return getattr(res, "data", None) or []
        except Exception as exc:
            logger.error("DB Error fetching cart items for cart %s: %s", cart_id, exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=CartSecurityMessages.DB_OPERATION_FAILED
            ) from exc

    async def get_product_stock_status(self, product_id: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("products").select(
                "id, name, price, compare_price, stock, hsn_code, gst_percentage, is_active"
            ).eq("id", product_id).limit(1).execute()
            data = getattr(res, "data", None)
            return data[0] if data and len(data) > 0 else None
        except Exception as exc:
            logger.error("DB Error checking stock for product %s: %s", product_id, exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=CartSecurityMessages.DB_OPERATION_FAILED
            ) from exc

    async def get_cart_item(self, cart_id: str, product_id: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("cart_items").select("id, quantity").eq("cart_id", cart_id).eq("product_id", product_id).limit(1).execute()
        data = getattr(res, "data", None)
        return data[0] if data and len(data) > 0 else None

    async def add_item_to_cart(self, cart_id: str, product_id: str, quantity: int, price_snapshot: float) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("cart_items").insert({
                "cart_id": cart_id, "product_id": product_id,
                "quantity": quantity, "price_snapshot": price_snapshot,
            }).execute()
            await self._touch_cart_timestamp(cart_id)
        except Exception as exc:
            logger.error("DB Error adding item to cart %s: %s", cart_id, exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=CartSecurityMessages.DB_OPERATION_FAILED) from exc

    async def update_item_quantity(self, cart_item_id: str, quantity: int) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("cart_items").update({"quantity": quantity}).eq("id", cart_item_id).execute()
            res = await admin_sb.table("cart_items").select("cart_id").eq("id", cart_item_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                await self._touch_cart_timestamp(res.data[0]["cart_id"])
        except Exception as exc:
            logger.error("DB Error updating cart item %s: %s", cart_item_id, exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=CartSecurityMessages.DB_OPERATION_FAILED) from exc

    async def update_item_quantity_by_product(self, cart_id: str, product_id: str, quantity: int) -> bool:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("cart_items").update({"quantity": quantity}).eq("cart_id", cart_id).eq("product_id", product_id).execute()
            await self._touch_cart_timestamp(cart_id)
            return bool(getattr(res, "data", None))
        except Exception as exc:
            logger.error("DB Error updating product %s in cart %s: %s", product_id, cart_id, exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=CartSecurityMessages.DB_OPERATION_FAILED) from exc

    async def remove_item(self, cart_id: str, product_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("cart_items").delete().eq("cart_id", cart_id).eq("product_id", product_id).execute()
            await self._touch_cart_timestamp(cart_id)
        except Exception as exc:
            logger.error("DB Error removing product %s from cart %s: %s", product_id, cart_id, exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=CartSecurityMessages.DB_OPERATION_FAILED) from exc

    async def clear_cart(self, cart_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("cart_items").delete().eq("cart_id", cart_id).execute()
            await self._touch_cart_timestamp(cart_id)
        except Exception as exc:
            logger.error("DB Error clearing cart %s: %s", cart_id, exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=CartSecurityMessages.DB_OPERATION_FAILED) from exc

    async def get_abandoned_carts(self, cutoff_iso: str, offset: int, page_size: int) -> Tuple[List[dict], int]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("carts").select(
                "id, user_id, updated_at, created_at, cart_items(id, quantity, price_snapshot, product_id), users(email, full_name)", count="exact"
            ).lt("updated_at", cutoff_iso).order("updated_at", desc=False).range(offset, offset + page_size - 1).execute()
            
            all_rows = getattr(res, "data", None) or []
            rows = [r for r in all_rows if r.get("cart_items") and len(r.get("cart_items")) > 0]
            return rows, res.count or 0
        except Exception as exc:
            logger.error("DB Error fetching abandoned carts: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=CartSecurityMessages.DB_OPERATION_FAILED) from exc

    async def get_cart_for_reminder(self, cart_id: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("carts").select(
                "id, user_id, cart_items(quantity, price_snapshot, products(name, image_url, slug)), users(email, full_name)"
            ).eq("id", cart_id).limit(1).execute()
            data = getattr(res, "data", None)
            return data[0] if data and len(data) > 0 else None
        except Exception as exc:
            logger.error("DB Error fetching cart reminder payload for %s: %s", cart_id, exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=CartSecurityMessages.DB_OPERATION_FAILED) from exc