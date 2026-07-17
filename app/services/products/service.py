"""
Product Service — Enterprise Catalog Engine
===========================================
Path: app/services/product_service.py
"""
import logging
import uuid
from typing import Any, Dict, Tuple, List
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.repositories.product_repo import AsyncProductRepository
from app.permissions.policies.product_policies import ProductPolicy
from app.constants.product_messages import ProductSecurityMessages
from app.services.image import upload_product_image, delete_product_image

logger = logging.getLogger(__name__)

class ProductService:
    def __init__(self):
        self.repo = AsyncProductRepository()

    async def get_categories(self) -> List[Dict[str, Any]]:
        return await self.repo.get_active_categories()

    async def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        res = await self.repo.create_category(data)
        if not res: 
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ProductSecurityMessages.DB_OPERATION_FAILED)
        return res

    async def delete_category(self, category_id: str) -> None:
        active_products = await self.repo.check_active_products_in_category(category_id)
        
        # Enforce ABAC State Policy
        ProductPolicy.assert_can_delete_category(active_products)
        
        if not await self.repo.soft_delete_category(category_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.CATEGORY_NOT_FOUND)

    async def get_products(self, page: int, page_size: int, category: str, search: str, min_p: float, max_p: float, in_stock: bool) -> Tuple[List[Dict[str, Any]], int]:
        return await self.repo.get_products(page, page_size, category, search, min_p, max_p, in_stock)

    async def get_product(self, slug: str) -> Dict[str, Any]:
        product = await self.repo.get_product_by_slug(slug)
        if not product: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)
        product["images"] = product.get("images") or []
        return product

    async def create_product(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if data.get("sku") and await self.repo.check_sku_exists(data["sku"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ProductSecurityMessages.SKU_COLLISION)
        
        data["slug"] = await self.repo.generate_unique_slug(data["slug"])
        data["price"] = float(data["price"])
        if data.get("compare_price"): 
            data["compare_price"] = float(data["compare_price"])
        data["images"] = data.get("images") or []

        res = await self.repo.create_product(data)
        if not res: 
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ProductSecurityMessages.DB_OPERATION_FAILED)
        return res

    async def update_product(self, product_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if "price" in data and data["price"]: 
            data["price"] = float(data["price"])
        if "compare_price" in data and data["compare_price"]: 
            data["compare_price"] = float(data["compare_price"])
            
        if "images" in data:
            imgs = data["images"] or []
            data["images"], data["image_url"] = imgs, imgs[0] if imgs else None

        res = await self.repo.update_product(product_id, data)
        if not res: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)
        return res

    async def delete_product(self, product_id: str) -> None:
        if not await self.repo.soft_delete_product(product_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)

    async def upload_image(self, product_id: str, contents: bytes, filename: str) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)

        existing = prod.get("images") or []
        
        # Enforce ABAC Limit Policy
        ProductPolicy.assert_can_upload_image(len(existing))

        try:
            url = await run_in_threadpool(upload_product_image, file_bytes=contents, product_id=product_id, filename=filename, generate_thumbnail=False)
        except Exception as e:
            logger.error("Cloud storage upload failed: %s", e)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=ProductSecurityMessages.UPLOAD_FAILED)

        all_images = existing + [url]
        await self.repo.update_product(product_id, {"images": all_images, "image_url": all_images[0]})
        return {"images": all_images, "image_url": all_images[0], "uploaded_url": url}

    async def delete_image(self, product_id: str, index: int) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)

        images = prod.get("images") or []
        if index < 0 or index >= len(images): 
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=ProductSecurityMessages.INVALID_IMAGE_INDEX)

        deleted_url = images.pop(index)
        new_primary = images[0] if images else None

        await self.repo.update_product(product_id, {"images": images, "image_url": new_primary})
        
        try: 
            await run_in_threadpool(delete_product_image, deleted_url)
        except Exception as e: 
            logger.warning("Storage delete warning (Non-fatal): %s", e)

        return {"images": images, "image_url": new_primary, "deleted_url": deleted_url}

    async def reorder_images(self, product_id: str, ordered_urls: List[str]) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ProductSecurityMessages.PRODUCT_NOT_FOUND)

        current = prod.get("images") or []
        
        # Enforce ABAC Integrity Policy
        ProductPolicy.assert_valid_image_reorder(current, ordered_urls)

        new_primary = ordered_urls[0] if ordered_urls else None
        await self.repo.update_product(product_id, {"images": ordered_urls, "image_url": new_primary})
        return {"images": ordered_urls, "image_url": new_primary}