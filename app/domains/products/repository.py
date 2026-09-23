"""
Product Domain Repository — Async Enterprise Grade (GST, HSN & SEO support).
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
        else:
            product["images"] = product.get("images") or []
        return self._format_product_seo(self._format_product_specs(product))

    def _format_product_specs(self, product: Dict[str, Any]) -> Dict[str, Any]:
        rows = product.pop("product_specifications", None) or []
        rows.sort(key=lambda x: x.get("position", 0))
        specs: Dict[str, Any] = {}
        for row in rows:
            code = row.get("specification_code")
            if not code:
                continue
            value = row.get("value_numeric")
            if value is None:
                value = row.get("value_text")
            if code in specs:
                if not isinstance(specs[code], list):
                    specs[code] = [specs[code]]
                specs[code].append(value)
            else:
                specs[code] = value
        product["specifications"] = specs
        for field in ("brand", "manufacturer", "model_number", "gtin", "ean", "part_number",
                      "material", "finish", "color", "size", "dimensions", "warranty"):
            product[field] = specs.get(field)
        return product

    def _format_product_seo(self, product: Dict[str, Any]) -> Dict[str, Any]:
        rows = product.pop("product_seo", None) or []
        seo = rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})
        product["seo_title"] = seo.get("title")
        product["seo_description"] = seo.get("description")
        product["canonical_url"] = seo.get("canonical_url")
        product["robots_index"] = seo.get("robots_index", True)
        product["robots_follow"] = seo.get("robots_follow", True)
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

    async def generate_unique_category_slug(self, base_slug: str) -> str:
        admin_sb = await get_async_admin_supabase()
        slug, counter = base_slug, 2
        while True:
            existing = await admin_sb.table("categories").select("id").eq("slug", slug).limit(1).execute()
            if not getattr(existing, "data", None):
                return slug
            slug = f"{base_slug}-{counter}"
            counter += 1

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
        # Listing cards only need these fields. Keep detail-only tax/SEO/image
        # relations out of the hot catalogue query to reduce DB work and payload.
        base_select = "id, name, slug, description, short_description, sku, category_id, price, compare_price, stock, weight, weight_unit, measurement_type, measurement_value, measurement_unit, image_url, is_active, hsn_code, gst_percentage, country_of_origin, {category_relation}, product_specifications(id, specification_code, value_text, value_numeric, unit_code, position), product_seo(product_id, title, description, canonical_url, robots_index, robots_follow)"
        category_relation = "categories!inner(name, slug)" if category_slug else "categories(name, slug)"
        q = admin_sb.table("products").select(
            base_select.format(category_relation=category_relation),
            count="exact",
        ).eq("is_active", True)
        if category_slug:
            # Filter through the embedded category relation instead of doing a
            # separate category-id lookup round trip.
            q = q.eq("categories.slug", category_slug)
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
        res = await admin_sb.table("products").select("id, name, slug, sku, category_id, description, short_description, price, compare_price, stock, weight, weight_unit, measurement_type, measurement_value, measurement_unit, image_url, is_active, hsn_code, gst_percentage, country_of_origin, product_specifications(id, specification_code, value_text, value_numeric, unit_code, position), product_seo(product_id, title, description, canonical_url, robots_index, robots_follow), product_images(id, url, alt, position), categories(name, slug)").eq("slug", slug).eq("is_active", True).limit(1).execute()
        data_list = getattr(res, "data", None)
        return self._format_product_images(data_list[0]) if data_list else None

    async def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select("id, name, slug, sku, price, compare_price, stock, hsn_code, gst_percentage, image_url, is_active, product_specifications(id, specification_code, value_text, value_numeric, unit_code, position), product_seo(product_id, title, description, canonical_url, robots_index, robots_follow), product_images(id, url, alt, position)").eq("id", product_id).limit(1).execute()
        data_list = getattr(res, "data", None)
        return self._format_product_images(data_list[0]) if data_list else None

    async def get_measurement_catalog(self) -> Dict[str, List[Dict[str, Any]]]:
        admin_sb = await get_async_admin_supabase()
        types_res = await admin_sb.table("measurement_types").select("code, name, value_kind").eq("is_active", True).order("name").execute()
        units_res = await admin_sb.table("measurement_units").select("code, measurement_type, name, symbol, is_base, multiplier").eq("is_active", True).order("name").execute()
        return {"types": getattr(types_res, "data", None) or [], "units": getattr(units_res, "data", None) or []}

    async def get_measurement_definition(self, measurement_type: str, measurement_unit: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("measurement_units").select("code, measurement_type, name, symbol, multiplier, is_active").eq("code", measurement_unit).eq("measurement_type", measurement_type).eq("is_active", True).limit(1).execute()
        data = getattr(res, "data", None) or []
        return data[0] if data else None

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
        payload = dict(data)
        image_urls = payload.pop("images", None) or []
        res = await admin_sb.table("products").insert(payload).execute()
        data_list = getattr(res, "data", None)
        if not data_list:
            return None
        product = data_list[0]
        product["images"] = image_urls
        return product

    async def update_product(self, product_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        payload = dict(data)
        image_urls = payload.pop("images", None)
        res = await admin_sb.table("products").update(payload).eq("id", product_id).execute()
        data_list = getattr(res, "data", None)
        if not data_list:
            return None
        product = data_list[0]
        if image_urls is not None:
            product["images"] = image_urls
        else:
            product["images"] = []
        return product

    async def soft_delete_product(self, product_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").update({"is_active": False}).eq("id", product_id).execute()
        return bool(getattr(res, "data", None))

    async def sync_product_specifications(self, product_id: str, rows: List[Dict[str, Any]]) -> None:
        admin_sb = await get_async_admin_supabase()
        await admin_sb.table("product_specifications").delete().eq("product_id", product_id).execute()
        if rows:
            payload = [dict(row, product_id=product_id, position=index) for index, row in enumerate(rows)]
            await admin_sb.table("product_specifications").insert(payload).execute()

    async def sync_product_seo(self, product_id: str, seo: Dict[str, Any]) -> None:
        admin_sb = await get_async_admin_supabase()
        clean = {k: v for k, v in seo.items() if v is not None}
        if not clean:
            await admin_sb.table("product_seo").delete().eq("product_id", product_id).execute()
            return
        clean["product_id"] = product_id
        await admin_sb.table("product_seo").upsert(clean, on_conflict="product_id").execute()

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
