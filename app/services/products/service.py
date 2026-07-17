import logging
import uuid
from typing import Any, Dict, Tuple, List
from starlette.concurrency import run_in_threadpool

from app.repositories.product_repo import AsyncProductRepository
from app.core.exceptions import ProductNotFound, LuviioException, OutOfStockException
from app.services.image import upload_product_image, delete_product_image

logger = logging.getLogger(__name__)
_MAX_IMAGES = 10

class ProductService:
    def __init__(self):
        self.repo = AsyncProductRepository()

    async def get_categories(self) -> List[Dict[str, Any]]:
        return await self.repo.get_active_categories()

    async def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        res = await self.repo.create_category(data)
        if not res: raise LuviioException("Failed to create category", "DB_ERROR", 500)
        return res

    async def delete_category(self, category_id: str) -> None:
        if await self.repo.check_active_products_in_category(category_id) > 0:
            raise LuviioException("Cannot delete — category has active products", "CATEGORY_NOT_EMPTY", 409)
        if not await self.repo.soft_delete_category(category_id):
            raise LuviioException("Failed to delete category", "DB_ERROR", 500)

    async def get_products(self, page: int, page_size: int, category: str, search: str, min_p: float, max_p: float, in_stock: bool) -> Tuple[List[Dict[str, Any]], int]:
        return await self.repo.get_products(page, page_size, category, search, min_p, max_p, in_stock)

    async def get_product(self, slug: str) -> Dict[str, Any]:
        product = await self.repo.get_product_by_slug(slug)
        if not product: raise ProductNotFound(slug)
        product["images"] = product.get("images") or []
        return product

    async def create_product(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if data.get("sku") and await self.repo.check_sku_exists(data["sku"]):
            raise LuviioException(f"SKU '{data['sku']}' already exists", "SKU_COLLISION", 409)
        
        data["slug"] = await self.repo.generate_unique_slug(data["slug"])
        data["price"] = float(data["price"])
        if data.get("compare_price"): data["compare_price"] = float(data["compare_price"])
        data["images"] = data.get("images") or []

        res = await self.repo.create_product(data)
        if not res: raise LuviioException("Failed to create product", "DB_ERROR", 500)
        return res

    async def update_product(self, product_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if "price" in data and data["price"]: data["price"] = float(data["price"])
        if "compare_price" in data and data["compare_price"]: data["compare_price"] = float(data["compare_price"])
        if "images" in data:
            imgs = data["images"] or []
            data["images"], data["image_url"] = imgs, imgs[0] if imgs else None

        res = await self.repo.update_product(product_id, data)
        if not res: raise ProductNotFound(product_id)
        return res

    async def delete_product(self, product_id: str) -> None:
        if not await self.repo.soft_delete_product(product_id):
            raise ProductNotFound(product_id)

    async def upload_image(self, product_id: str, contents: bytes, filename: str) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: raise ProductNotFound(product_id)

        existing = prod.get("images") or []
        if len(existing) >= _MAX_IMAGES: 
            raise LuviioException(f"Max {_MAX_IMAGES} images allowed", "LIMIT_EXCEEDED", 400)

        try:
            url = await run_in_threadpool(upload_product_image, file_bytes=contents, product_id=product_id, filename=filename, generate_thumbnail=False)
        except Exception as e:
            raise LuviioException(str(e), "UPLOAD_FAILED", 500)

        all_images = existing + [url]
        await self.repo.update_product(product_id, {"images": all_images, "image_url": all_images[0]})
        return {"images": all_images, "image_url": all_images[0], "uploaded_url": url}

    async def delete_image(self, product_id: str, index: int) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: raise ProductNotFound(product_id)

        images = prod.get("images") or []
        if index < 0 or index >= len(images): 
            raise LuviioException("Index out of range", "INVALID_INDEX", 400)

        deleted_url = images.pop(index)
        new_primary = images[0] if images else None

        await self.repo.update_product(product_id, {"images": images, "image_url": new_primary})
        
        try: await run_in_threadpool(delete_product_image, deleted_url)
        except Exception as e: logger.warning(f"Storage delete warning: {e}")

        return {"images": images, "image_url": new_primary, "deleted_url": deleted_url}

    async def reorder_images(self, product_id: str, ordered_urls: List[str]) -> Dict[str, Any]:
        prod = await self.repo.get_product_by_id(product_id)
        if not prod: raise ProductNotFound(product_id)

        current = prod.get("images") or []
        if set(ordered_urls) != set(current): 
            raise LuviioException("URLs must match existing images exactly", "INVALID_PAYLOAD", 400)

        new_primary = ordered_urls[0] if ordered_urls else None
        await self.repo.update_product(product_id, {"images": ordered_urls, "image_url": new_primary})
        return {"images": ordered_urls, "image_url": new_primary}