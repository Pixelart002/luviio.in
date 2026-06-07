"""
Cart Repository
===============
Path: app/repositories/cart_repo.py
"""
import logging
from typing import Any
from .base import BaseRepository

logger = logging.getLogger(__name__)

class CartRepository(BaseRepository):
    
    def get_pricing_config(self) -> dict[str, Any]:
        try:
            res = self.admin_sb.table("pricing_config").select("*").limit(1).single().execute()
            return res.data if res and res.data else {}
        except Exception:
            return {}

    def get_or_create_cart(self, user_id: str) -> dict[str, Any]:
        self.admin_sb.table("carts").upsert(
            {"user_id": user_id}, on_conflict="user_id", ignore_duplicates=True
        ).execute()
        
        fetch = self.admin_sb.table("carts").select("*").eq("user_id", user_id).limit(1).execute()
        return fetch.data[0]

    def get_cart_items_with_products(self, cart_id: str) -> list[dict[str, Any]]:
        res = self.admin_sb.table("cart_items").select(
            "id, product_id, quantity, price_snapshot, added_at, "
            "products(id, name, slug, price, stock, image_url, is_active)"
        ).eq("cart_id", cart_id).order("added_at", desc=False).execute()
        return getattr(res, "data", None) or []

    def get_product_stock_status(self, product_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("products").select("id, name, price, stock, is_active").eq("id", product_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None

    def get_cart_item(self, cart_id: str, product_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("cart_items").select("id, quantity").eq("cart_id", cart_id).eq("product_id", product_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None

    def add_item_to_cart(self, cart_id: str, product_id: str, quantity: int, price_snapshot: float) -> None:
        self.admin_sb.table("cart_items").insert({
            "cart_id": cart_id, "product_id": product_id,
            "quantity": quantity, "price_snapshot": price_snapshot,
        }).execute()

    def update_item_quantity(self, cart_item_id: str, quantity: int) -> None:
        self.admin_sb.table("cart_items").update({"quantity": quantity}).eq("id", cart_item_id).execute()

    def update_item_quantity_by_product(self, cart_id: str, product_id: str, quantity: int) -> bool:
        res = self.admin_sb.table("cart_items").update({"quantity": quantity}).eq("cart_id", cart_id).eq("product_id", product_id).execute()
        return bool(getattr(res, "data", None))

    def remove_item(self, cart_id: str, product_id: str) -> None:
        self.admin_sb.table("cart_items").delete().eq("cart_id", cart_id).eq("product_id", product_id).execute()

    def clear_cart(self, cart_id: str) -> None:
        self.admin_sb.table("cart_items").delete().eq("cart_id", cart_id).execute()

    def get_abandoned_carts(self, cutoff_iso: str, offset: int, page_size: int) -> tuple[list, int]:
        res = self.admin_sb.table("carts").select(
            "id, user_id, updated_at, created_at, cart_items(id, quantity, price_snapshot, product_id), users(email, full_name)", count="exact"
        ).lt("updated_at", cutoff_iso).order("updated_at", desc=False).range(offset, offset + page_size - 1).execute()
        
        all_rows = getattr(res, "data", None) or []
        rows = [r for r in all_rows if r.get("cart_items")]
        return rows, res.count or 0

    def get_cart_for_reminder(self, cart_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("carts").select(
            "id, user_id, cart_items(quantity, price_snapshot, products(name, image_url, slug)), users(email, full_name)"
        ).eq("id", cart_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None