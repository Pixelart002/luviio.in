"""
Product Service — Async Enterprise Grade
========================================
Path: app/services/products/service.py
"""
import logging
from typing import Any, Dict, List, Tuple
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.repositories.product_repo import AsyncProductRepository
from app.permissions.policies.product_policy import ProductPolicy
from app.constants.product_messages import ProductSecurityMessages
from app.services.image import upload_product_image, delete_product_image

logger = logging.getLogger(__name__)

class ProductService:
    def __init__(self) -> None:
        self.repo = AsyncProductRepository()

    def _enrich_discount(self, prod: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures immediate discount availability for in-memory DTOs."""
        if not prod:
            return prod
        try:
            price = float(prod.get("price") or 0.0)
            compare = float(prod.get("compare_price") or 0.0)
            if compare > price > 0:
                disc_amt = round(compare - price, 2)
                disc_pct = int(round((disc_amt / compare) * 100))
            else:
                disc_amt = 0.0
                disc_pct = 0
            prod["discount_amount"] = disc_amt
            prod["discount_percentage"] = disc_pct
        except (ValueError, TypeError):
            prod["discount_amount"] = 0.0
            prod["discount_percentage"] = 0
        return prod

    # ── Categories ───────────────────────────────────────────────────────────
    async def get_categories(self) -> List[Dict[str, Any]]:
        return await self.repo.get_active_categories()

    async def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        res = await self.repo.create_category(data)
        if not res: 
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ProductSecurityMessages.DB_OPERATION_FAILED)
        return res

    async def delete_category(self, category_id: str) -> None:
        active_products = await self.repo.check_active_products_in_category(category_id)
        ProductPolicy.assert_can_delete_category(active_products)
        
        if not await self.repo.soft_delete_category(category_id):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ProductSecurityMessages.DB_OPERATION_FAILED)

    # ── Products ─────────────────────────────────────────────────────────────
    async def get_products(self, page: int, page_size: int, category: str, search: str, min_p: float, max_p: float, in_stock: bool) -> Tuple[List[Dict[str, Any]], int]:
        products, total = await self.repo.get_products(page, page_size, category, search, min_p, max_p, in_stock)
        return [self._enrich_discount(p) for p in products], total

    async def get_product(self, slug: str) -> Dict[str, Any]:
        product = await self.repo.get_product_by_slug(slug)
        if not product: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)
        product["images"] = product.get("images") or []
        return self._enrich_discount(product)

    async def create_product(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if data.get("sku") and await self.repo.check_sku_exists(data["sku"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ProductSecurityMessages.SKU_COLLISION)
        
        data["slug"] = await self.repo.generate_unique_slug(data["slug"])
        data["price"] = float(data["price"])
        if data.get("compare_price"): 
            data["compare_price"] = float(data["compare_price"])
        data["images"] = data.get("images") or []
        data["image_url"] = data["images"][0] if data["images"] else None
        data["hsn_code"] = str(data.get("hsn_code") or "9988").strip()
        data["gst_percentage"] = int(data.get("gst_percentage") if data.get("gst_percentage") is not None else 18)

        res = await self.repo.create_product(data)
        if not res: 
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ProductSecurityMessages.DB_OPERATION_FAILED)
            
        await self.repo.sync_product_images_table(res["id"], res.get("images") or [])
        return self._enrich_discount(res)

    async def update_product(self, product_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if "sku" in data and data["sku"]:
            if await self.repo.check_sku_exists(data["sku"], exclude_product_id=product_id):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ProductSecurityMessages.SKU_COLLISION)

        if "slug" in data and data["slug"]:
            data["slug"] = await self.repo.generate_unique_slug(data["slug"], exclude_product_id=product_id)
        if "price" in data and data["price"] is not None: 
            data["price"] = float(data["price"])
        if "compare_price" in data and data["compare_price"] is not None: 
            data["compare_price"] = float(data["compare_price"])
        if "gst_percentage" in data and data["gst_percentage"] is not None:
            data["gst_percentage"] = int(data["gst_percentage"])
        if "hsn_code" in data and data["hsn_code"]:
            data["hsn_code"] = str(data["hsn_code"]).strip()
            
        if "images" in data:
            imgs = data["images"] or []
            data["images"], data["image_url"] = imgs, imgs[0] if imgs else None

        res = await self.repo.update_product(product_id, data)
        if not res: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)
            
        if "images" in data:
            await self.repo.sync_product_images_table(product_id, res.get("images") or [])
            
        return self._enrich_discount(res)

    async def delete_product(self, product_id: str) -> None:
        if not await self.repo.soft_delete_product(product_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)

    # ── Images ───────────────────────────────────────────────────────────────
    async def upload_image(self, product_id: str, contents: bytes, filename: str) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)

        existing = prod.get("images") or []
        ProductPolicy.assert_can_upload_image(len(existing))

        try:
            url = await run_in_threadpool(upload_product_image, file_bytes=contents, product_id=product_id, filename=filename, generate_thumbnail=False)
        except Exception as exc:
            logger.error("Image upload failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=ProductSecurityMessages.UPLOAD_FAILED) from exc

        all_images = existing + [url]
        await self.repo.update_product(product_id, {"images": all_images, "image_url": all_images[0]})
        await self.repo.sync_product_images_table(product_id, all_images)
        return {"images": all_images, "image_url": all_images[0], "uploaded_url": url}

    async def delete_image(self, product_id: str, index: int) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)

        images = prod.get("images") or []
        ProductPolicy.assert_valid_image_index(index, len(images))

        deleted_url = images.pop(index)
        new_primary = images[0] if images else None

        await self.repo.update_product(product_id, {"images": images, "image_url": new_primary})
        await self.repo.sync_product_images_table(product_id, images)
        
        try: 
            await run_in_threadpool(delete_product_image, deleted_url)
        except Exception as exc: 
            logger.warning("Storage delete warning: %s", exc)

        return {"images": images, "image_url": new_primary, "deleted_url": deleted_url}

    async def reorder_images(self, product_id: str, ordered_urls: List[str]) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)

        current = prod.get("images") or []
        ProductPolicy.assert_valid_image_reorder(current, ordered_urls)

        new_primary = ordered_urls[0] if ordered_urls else None
        await self.repo.update_product(product_id, {"images": ordered_urls, "image_url": new_primary})
        await self.repo.sync_product_images_table(product_id, ordered_urls)
        return {"images": ordered_urls, "image_url": new_primary}