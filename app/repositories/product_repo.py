"""
Product Repository — Async Enterprise Grade (With GST & HSN Support)
====================================================================
Path: app/repositories/product_repo.py

Architecture & Fixes:
  ✅ Stateless Execution — Fetches Supabase Admin client on-demand inside async methods.
  ✅ Resolves Coroutine Crash — Awaits async client factory to prevent AttributeError.
  ✅ GST & HSN Ready — Explicitly selects hsn_code and gst_percentage for invoice & checkout mapping.
  ✅ Checkout Snapshot Safe — Upgraded get_product_by_id to fetch full pricing & tax fields.
"""
import logging
from typing import Any
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncProductRepository:
    def __init__(self):
        # Deferred client initialization to prevent coroutine AttributeError in sync constructor
        pass
    
    # ── Categories ───────────────────────────────────────────────────────────
    async def get_active_categories(self) -> list[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("categories").select("*").eq("is_active", True).execute()
        return getattr(res, "data", None) or []

    async def create_category(self, data: dict) -> dict[str, Any] | None:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("categories").insert(data).execute()
        return res.data[0] if getattr(res, "data", None) else None

    async def check_active_products_in_category(self, category_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select("id", count="exact").eq("category_id", category_id).eq("is_active", True).limit(1).execute()
        return res.count or 0

    async def soft_delete_category(self, category_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("categories").update({"is_active": False}).eq("id", category_id).execute()
        return bool(getattr(res, "data", None))

    # ── Products ─────────────────────────────────────────────────────────────
    async def get_products(
        self, 
        page: int, 
        page_size: int, 
        category_slug: str | None, 
        search: str | None, 
        min_price: float | None, 
        max_price: float | None, 
        in_stock: bool | None
    ) -> tuple[list, int]:
        admin_sb = await get_async_admin_supabase()
        
        # 🔥 UPGRADE: Added hsn_code and gst_percentage to product listings
        q = admin_sb.table("products").select(
            "id, name, slug, short_description, sku, category_id, price, compare_price, stock, low_stock_threshold, weight_grams, image_url, images, is_active, created_at, hsn_code, gst_percentage, categories(name, slug)",
            count="exact"
        ).eq("is_active", True)

        if category_slug:
            cat = await admin_sb.table("categories").select("id").eq("slug", category_slug).limit(1).execute()
            if cat and getattr(cat, "data", None):
                q = q.eq("category_id", cat.data[0]["id"])
            else:
                return [], 0

        if search: q = q.ilike("name", f"%{search}%")
        if min_price is not None: q = q.gte("price", min_price)
        if max_price is not None: q = q.lte("price", max_price)
        if in_stock: q = q.gt("stock", 0)

        offset = (page - 1) * page_size
        res = await q.range(offset, offset + page_size - 1).execute()
        return getattr(res, "data", None) or [], res.count or 0

    async def get_product_by_slug(self, slug: str) -> dict[str, Any] | None:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select("*, categories(name, slug)").eq("slug", slug).eq("is_active", True).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None
        
    async def get_product_by_id(self, product_id: str) -> dict[str, Any] | None:
        """
        🔥 UPGRADE: Fetches full tax & pricing snapshot data (name, price, hsn_code, gst_percentage)
        so checkout and invoice generators can safely lock down values during order creation.
        """
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select(
            "id, name, slug, sku, price, compare_price, stock, hsn_code, gst_percentage, images, is_active"
        ).eq("id", product_id).limit(1).execute()
        return res.data[0] if getattr(res, "data", None) else None

    async def check_sku_exists(self, sku: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select("id").eq("sku", sku).limit(1).execute()
        return bool(getattr(res, "data", None))

    async def generate_unique_slug(self, base_slug: str) -> str:
        admin_sb = await get_async_admin_supabase()
        slug, counter = base_slug, 2
        while True:
            existing = await admin_sb.table("products").select("id").eq("slug", slug).limit(1).execute()
            if not getattr(existing, "data", None): return slug
            slug = f"{base_slug}-{counter}"
            counter += 1

    async def create_product(self, data: dict) -> dict[str, Any] | None:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").insert(data).execute()
        return res.data[0] if getattr(res, "data", None) else None

    async def update_product(self, product_id: str, data: dict) -> dict[str, Any] | None:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").update(data).eq("id", product_id).execute()
        return res.data[0] if getattr(res, "data", None) else None

    async def soft_delete_product(self, product_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").update({"is_active": False}).eq("id", product_id).execute()
        return bool(getattr(res, "data", None))