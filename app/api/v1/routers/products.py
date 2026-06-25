"""
Products Router — Async Enterprise Grade
========================================
Path: app/api/v1/routers/products.py

🔥 OBSERVABILITY UPGRADE: Saturated all Catalog CRUD operations and Image 
   threadpool offloading with explicit actions for PureWindowLogger.
"""
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from starlette.concurrency import run_in_threadpool

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import require_admin
from app.repositories.product_repo import AsyncProductRepository
from app.api.schemas.product_dto import CategoryCreate, ProductCreate, ProductUpdate, MessageResponse
from app.services.image import upload_product_image, delete_product_image

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Products"])
_MAX_IMAGES = 10

# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/categories")
async def list_categories(request: Request) -> list[dict[str, Any]]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Fetching active product categories from Global Catalog")

    return await AsyncProductRepository().get_active_categories()

@router.post("/categories", status_code=201, dependencies=[Depends(require_admin)])
async def create_category(request: Request, payload: CategoryCreate) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin creating new category -> '{payload.name}'")

    repo = AsyncProductRepository()
    res = await repo.create_category(payload.model_dump())
    if not res: raise HTTPException(500, "Failed to create category")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Category created successfully in database")

    return res

@router.delete("/categories/{category_id}", dependencies=[Depends(require_admin)], response_model=MessageResponse)
async def delete_category(request: Request, category_id: uuid.UUID) -> dict[str, str]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin initiating deletion for Category: {str(category_id)[:8]}...")

    repo = AsyncProductRepository()
    if await repo.check_active_products_in_category(str(category_id)) > 0:
        if hasattr(request.state, "actions"):
            request.state.actions.append("❌ Aborted: Category still contains active products")
        raise HTTPException(409, "Cannot delete — category has active products")
        
    if not await repo.soft_delete_category(str(category_id)):
        raise HTTPException(500, "Failed to delete category")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Category soft-deleted successfully")

    return {"message": "Category deleted"}

# ══════════════════════════════════════════════════════════════════════════════
#  PRODUCTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/products")
async def list_products(
    request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None), search: str | None = Query(None),
    min_price: float | None = Query(None, ge=0), max_price: float | None = Query(None, ge=0),
    in_stock: bool | None = None,
) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Querying Paginated Catalog (Page: {page}, Category: {category or 'All'})")

    repo = AsyncProductRepository()
    items, total = await repo.get_products(page, page_size, category, search, min_price, max_price, in_stock)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Retrieved {len(items)} products from inventory")

    return {
        "items": items, "total": total, "page": page, "page_size": page_size, 
        "pages": -(-total // page_size) if page_size > 0 else 0,
    }

@router.get("/products/{slug}")
async def get_product(request: Request, slug: str) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Targeting Product detail fetch for slug -> '{slug}'")

    product = await AsyncProductRepository().get_product_by_slug(slug)
    if not product: 
        if hasattr(request.state, "actions"):
            request.state.actions.append("❌ Aborted: Product slug not found")
        raise HTTPException(404, "Product not found")
        
    product["images"] = product.get("images") or []
    return product

@router.post("/products", status_code=201, dependencies=[Depends(require_admin)])
async def create_product(request: Request, payload: ProductCreate) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin inserting new product -> SKU: {payload.sku or 'Auto'}")

    repo = AsyncProductRepository()
    
    if payload.sku and await repo.check_sku_exists(payload.sku):
        if hasattr(request.state, "actions"):
            request.state.actions.append("❌ Aborted: SKU collision detected")
        raise HTTPException(409, f"SKU '{payload.sku}' already exists")

    data = payload.model_dump()
    data["slug"] = await repo.generate_unique_slug(data["slug"])
    data["price"] = float(data["price"])
    if data.get("compare_price"): data["compare_price"] = float(data["compare_price"])
    data["images"] = data.get("images") or []

    res = await repo.create_product(data)
    if not res: raise HTTPException(500, "Failed to create product")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Product committed successfully -> Slug assigned: {data['slug']}")

    return res

@router.patch("/products/{product_id}", dependencies=[Depends(require_admin)])
async def update_product(request: Request, product_id: uuid.UUID, payload: ProductUpdate) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin overriding Product metadata -> ID: {str(product_id)[:8]}...")

    repo = AsyncProductRepository()
    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}

    if "price" in data and data["price"]: data["price"] = float(data["price"])
    if "compare_price" in data and data["compare_price"]: data["compare_price"] = float(data["compare_price"])
    if "images" in data:
        imgs = data["images"] or []
        data["images"], data["image_url"] = imgs, imgs[0] if imgs else None

    res = await repo.update_product(str(product_id), data)
    if not res: 
        raise HTTPException(404, "Product not found")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Metadata override synchronized with database")

    return res

@router.delete("/products/{product_id}", dependencies=[Depends(require_admin)], response_model=MessageResponse)
async def delete_product(request: Request, product_id: uuid.UUID) -> dict[str, str]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin initiating soft-deletion for Product -> ID: {str(product_id)[:8]}...")

    if not await AsyncProductRepository().soft_delete_product(str(product_id)):
        raise HTTPException(404, "Product not found")
        
    if hasattr(request.state, "actions"):
        request.state.actions.append("Product effectively isolated from global catalog")

    return {"message": "Product deleted"}

# ══════════════════════════════════════════════════════════════════════════════
#  IMAGES
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/products/{product_id}/images", dependencies=[Depends(require_admin)])
async def upload_image_endpoint(request: Request, product_id: uuid.UUID, file: UploadFile = File(...)) -> dict[str, Any]:
    pid = str(product_id)
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Receiving asset upload for Product: {pid[:8]}... (File: {file.filename})")

    repo = AsyncProductRepository()
    prod = await repo.get_product_by_id(pid)
    
    if not prod: raise HTTPException(404, "Product not found")

    existing = prod.get("images") or []
    if len(existing) >= _MAX_IMAGES: 
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"❌ Aborted: Catalog image capacity reached ({_MAX_IMAGES} images)")
        raise HTTPException(400, f"Max {_MAX_IMAGES} images allowed")

    contents = await file.read()
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Offloading heavy image encoding & Cloud Storage upload to Threadpool")

    try:
        url = await run_in_threadpool(
            upload_product_image, file_bytes=contents, product_id=pid, filename=file.filename or "unknown", generate_thumbnail=False
        )
    except ValueError as e: raise HTTPException(400, str(e))
    except RuntimeError as e: raise HTTPException(500, str(e))

    all_images = existing + [url]
    await repo.update_product(pid, {"images": all_images, "image_url": all_images[0]})
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Cloud URL acquired -> Appending to DB image ledger")

    return {"images": all_images, "image_url": all_images[0], "uploaded_url": url}

@router.delete("/products/{product_id}/images/{index}", dependencies=[Depends(require_admin)])
async def delete_image_endpoint(request: Request, product_id: uuid.UUID, index: int) -> dict[str, Any]:
    pid = str(product_id)
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin targeting Image deletion at Index [{index}] for Product: {pid[:8]}...")

    repo = AsyncProductRepository()
    prod = await repo.get_product_by_id(pid)
    if not prod: raise HTTPException(404, "Product not found")

    images = prod.get("images") or []
    if index < 0 or index >= len(images): raise HTTPException(400, f"Index {index} out of range (0-{len(images)-1})")

    deleted_url = images.pop(index)
    new_primary = images[0] if images else None

    await repo.update_product(pid, {"images": images, "image_url": new_primary})
    if hasattr(request.state, "actions"):
        request.state.actions.append("Excised asset URL from DB ledger")

    try: 
        if hasattr(request.state, "actions"):
            request.state.actions.append("Offloading Cloud Storage asset purge to background Threadpool")
        await run_in_threadpool(delete_product_image, deleted_url)
    except Exception as e: 
        logger.warning(f"Storage delete warning: {e}")
    
    return {"images": images, "image_url": new_primary, "deleted_url": deleted_url}

@router.put("/products/{product_id}/images/reorder", dependencies=[Depends(require_admin)])
async def reorder_images(request: Request, product_id: uuid.UUID, ordered_urls: list[str]) -> dict[str, Any]:
    pid = str(product_id)
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin restructuring image carousel array for Product: {pid[:8]}...")

    repo = AsyncProductRepository()
    prod = await repo.get_product_by_id(pid)
    if not prod: raise HTTPException(404, "Product not found")

    current = prod.get("images") or []
    if set(ordered_urls) != set(current): raise HTTPException(400, "URLs must match existing images exactly")

    new_primary = ordered_urls[0] if ordered_urls else None
    await repo.update_product(pid, {"images": ordered_urls, "image_url": new_primary})

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Carousel array synchronized -> Primary image recomputed")

    return {"images": ordered_urls, "image_url": new_primary}