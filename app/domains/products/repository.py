"""
Product Domain Repository — Async Enterprise Grade (GST & HSN support).
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncProductRepository:
    def __init__(self) -> None:
        pass

    def _format_product_images(self, product: Dict[str, Any]) -> Dict[str, Any]:
        if "product_images" in product:
            imgs = product.pop("product_images") or []
            imgs.sort(key=lambda x: x.get("position", 0) if x.get("position") is not None else 0)
            product["images"] = [img["url"] for img in imgs if "url" in img]
        return product

    async def get_active_categories(self) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("categories").select("*").eq("is_active", True).execute()
        return getattr(res, "data", None) or []

    async def create_category(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("categories").insert(data).execute()
        data_list = getattr(res, "data", None)
        return data_list[0] if data_list else None

    async def check_active_products_in_category(self, category_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select("id", count="exact").eq("category_id", category_id).eq("is_active", True).limit(1).execute()
        return res.count or 0

    async def soft_delete_category(self, category_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("categories").update({"is_active": False}).eq("id", category_id).execute()
        return bool(getattr(res, "data", None))

    async def get_products(self, page: int, page_size: int, category_slug: Optional[str], search: Optional[str], min_price: Optional[float], max_price: Optional[float], in_stock: Optional[bool]) -> Tuple[List[Dict[str, Any]], int]:
        admin_sb = await get_async_admin_supabase()
        q = admin_sb.table("products").select("id, name, slug, short_description, sku, category_id, price, compare_price, stock, low_stock_threshold, weight_grams, image_url, attributes, is_active, created_at, hsn_code, gst_percentage, discount_amount, discount_percentage, categories(name, slug), product_images(id, url, alt, position)", count="exact").eq("is_active", True)
        if category_slug:
            cat = await admin_sb.table("categories").select("id").eq("slug", category_slug).limit(1).execute()
            if cat and getattr(cat, "data", None):
                q = q.eq("category_id", cat.data[0]["id"])
            else:
                return [], 0
        if search:
            q = q.ilike("name", f"%{search}%")
        if min_price is not None:
            q = q.gte("price", min_price)
        if max_price is not None:
            q = q.lte("price", max_price)
        if in_stock:
            q = q.gt("stock", 0)
        offset = (page - 1) * page_size
        res = await q.range(offset, offset + page_size - 1).execute()
        raw_products = getattr(res, "data", None) or []
        return [self._format_product_images(p) for p in raw_products], res.count or 0

    async def get_product_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select("*, categories(name, slug), product_images(id, url, alt, position)").eq("slug", slug).eq("is_active", True).limit(1).execute()
        data_list = getattr(res, "data", None)
        return self._format_product_images(data_list[0]) if data_list else None

    async def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select("id, name, slug, sku, price, compare_price, stock, hsn_code, gst_percentage, image_url, attributes, is_active, product_images(id, url, alt, position)").eq("id", product_id).limit(1).execute()
        data_list = getattr(res, "data", None)
        return self._format_product_images(data_list[0]) if data_list else None

    async def check_sku_exists(self, sku: str, exclude_product_id: Optional[str] = None) -> bool:
        admin_sb = await get_async_admin_supabase()
        q = admin_sb.table("products").select("id").eq("sku", sku)
        if exclude_product_id:
            q = q.neq("id", exclude_product_id)
        res = await q.limit(1).execute()
        return bool(getattr(res, "data", None))

    async def generate_unique_slug(self, base_slug: str, exclude_product_id: Optional[str] = None) -> str:
        admin_sb = await get_async_admin_supabase()
        slug, counter = base_slug, 2
        while True:
            q = admin_sb.table("products").select("id").eq("slug", slug)
            if exclude_product_id:
                q = q.neq("id", exclude_product_id)
            existing = await q.limit(1).execute()
            if not getattr(existing, "data", None):
                return slug
            slug = f"{base_slug}-{counter}"
            counter += 1

    async def create_product(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        safe_data = dict(data)
        safe_data.pop("images", None)
        res = await admin_sb.table("products").insert(safe_data).execute()
        data_list = getattr(res, "data", None)
        return data_list[0] if data_list else None

    async def update_product(self, product_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        safe_data = dict(data)
        safe_data.pop("images", None)
        res = await admin_sb.table("products").update(safe_data).eq("id", product_id).execute()
        data_list = getattr(res, "data", None)
        return data_list[0] if data_list else None

    async def soft_delete_product(self, product_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").update({"is_active": False}).eq("id", product_id).execute()
        return bool(getattr(res, "data", None))

    async def sync_product_images_table(self, product_id: str, image_urls: List[str]) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("product_images").delete().eq("product_id", product_id).execute()
            if image_urls:
                records = [{"product_id": product_id, "url": url, "position": idx} for idx, url in enumerate(image_urls)]
                await admin_sb.table("product_images").insert(records).execute()
        except Exception as exc:
            logger.warning("Non-fatal: Failed to sync relational product_images for %s: %s", product_id, exc)

    async def get_product_variants(self, product_id: str) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("product_variants").select("*").eq("product_id", product_id).eq("is_active", True).execute()
        return getattr(res, "data", None) or []

    async def create_product_variant(self, product_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        data["product_id"] = product_id
        res = await admin_sb.table("product_variants").insert(data).execute()
        data_list = getattr(res, "data", None)
        return data_list[0] if data_list else None

    async def update_product_variant(self, variant_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("product_variants").update(data).eq("id", variant_id).execute()
        data_list = getattr(res, "data", None)
        return data_list[0] if data_list else None

    async def delete_product_variant(self, variant_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("product_variants").delete().eq("id", variant_id).execute()
        return bool(getattr(res, "data", None))
