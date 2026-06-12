"""
Cart Repository — Async Enterprise Grade
========================================
Path: app/repositories/cart_repo.py
"""
import logging
from typing import Any, Tuple, List
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncCartRepository:
    def __init__(self):
        self.admin_sb = get_async_admin_supabase()
    
    async def get_pricing_config(self) -> dict[str, Any]:
        try:
            res = await self.admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
            return res.data if res and res.data else {}
        except Exception:
            return {}

    async def get_or_create_cart(self, user_id: str) -> dict[str, Any]:
        res = await self.admin_sb.table("carts").upsert(
            {"user_id": user_id}, on_conflict="user_id"
        ).execute()
        return res.data[0]

    async def is_cart_locked(self, user_id: str) -> bool:
        """Return True if the user's cart is locked (checkout in progress)."""
        res = await self.admin_sb.table("carts").select("locked").eq("user_id", user_id).maybe_single().execute()
        return bool(res and res.data and res.data.get("locked", False))

    async def get_cart_items_with_products(self, cart_id: str) -> list[dict[str, Any]]:
        res = await self.admin_sb.table("cart_items").select(
            "id, product_id, quantity, price_snapshot, added_at, "
            "products(id, name, slug, price, stock, image_url, is_active)"
        ).eq("cart_id", cart_id).order("added_at", desc=False).execute()
        return getattr(res, "data", None) or []

    async def get_product_stock_status(self, product_id: str) -> dict[str, Any] | None:
        res = await self.admin_sb.table("products").select("id, name, price, stock, is_active").eq("id", product_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None

    async def get_cart_item(self, cart_id: str, product_id: str) -> dict[str, Any] | None:
        res = await self.admin_sb.table("cart_items").select("id, quantity").eq("cart_id", cart_id).eq("product_id", product_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None

    async def add_item_to_cart(self, cart_id: str, product_id: str, quantity: int, price_snapshot: float) -> None:
        await self.admin_sb.table("cart_items").insert({
            "cart_id": cart_id, "product_id": product_id,
            "quantity": quantity, "price_snapshot": price_snapshot,
        }).execute()

    async def update_item_quantity(self, cart_item_id: str, quantity: int) -> None:
        await self.admin_sb.table("cart_items").update({"quantity": quantity}).eq("id", cart_item_id).execute()

    async def update_item_quantity_by_product(self, cart_id: str, product_id: str, quantity: int) -> bool:
        res = await self.admin_sb.table("cart_items").update({"quantity": quantity}).eq("cart_id", cart_id).eq("product_id", product_id).execute()
        return bool(getattr(res, "data", None))

    async def remove_item(self, cart_id: str, product_id: str) -> None:
        await self.admin_sb.table("cart_items").delete().eq("cart_id", cart_id).eq("product_id", product_id).execute()

    async def clear_cart(self, cart_id: str) -> None:
        await self.admin_sb.table("cart_items").delete().eq("cart_id", cart_id).execute()

    async def get_abandoned_carts(self, cutoff_iso: str, offset: int, page_size: int) -> Tuple[List[dict], int]:
        res = await self.admin_sb.table("carts").select(
            "id, user_id, updated_at, created_at, cart_items(id, quantity, price_snapshot, product_id), users(email, full_name)", count="exact"
        ).lt("updated_at", cutoff_iso).order("updated_at", desc=False).range(offset, offset + page_size - 1).execute()
        
        all_rows = getattr(res, "data", None) or []
        rows = [r for r in all_rows if r.get("cart_items")]
        return rows, res.count or 0

    async def get_cart_for_reminder(self, cart_id: str) -> dict[str, Any] | None:
        res = await self.admin_sb.table("carts").select(
            "id, user_id, cart_items(quantity, price_snapshot, products(name, image_url, slug)), users(email, full_name)"
        ).eq("id", cart_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None