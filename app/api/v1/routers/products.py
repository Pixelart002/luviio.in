"""
Product Router — Async Hardened Production Grade
================================================
Path: app/api/v1/routers/products.py
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status

from app.core.dependencies import require_permission
from app.permissions.products import ProductPermissions
from app.services.products.service import ProductService
from app.api.schemas.product_dto import CategoryCreate, ProductCreate, ProductUpdate
from app.constants.product_messages import ProductMessages
from app.utils.response import success_response
from app.utils.pagination import paginate

router = APIRouter(prefix="/products", tags=["Products"])

@router.get("/categories", status_code=status.HTTP_200_OK)
async def list_categories(request: Request):
    """Publicly accessible endpoint to fetch all active product categories."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Fetching active product categories from Global Catalog")
    return success_response(await ProductService().get_categories())

@router.post("/categories", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission(ProductPermissions.CREATE))])
async def create_category(request: Request, payload: CategoryCreate):
    """PBAC Guarded: Create a new product category."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin creating new category -> '{payload.name}'")
    
    result = await ProductService().create_category(payload.model_dump())
    return success_response(data=result, message=ProductMessages.CATEGORY_CREATED)

@router.delete("/categories/{category_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.DELETE))])
async def delete_category(request: Request, category_id: uuid.UUID):
    """PBAC Guarded: Soft deletes a category (ABAC enforces active products == 0)."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin initiating deletion for Category: {str(category_id)[:8]}...")
        
    await ProductService().delete_category(str(category_id))
    return success_response(message=ProductMessages.CATEGORY_DELETED)

@router.get("", status_code=status.HTTP_200_OK)
async def list_products(
    request: Request, 
    page: int = Query(1, ge=1), 
    page_size: int = Query(20, ge=1, le=100), 
    category: Optional[str] = Query(None), 
    search: Optional[str] = Query(None), 
    min_price: Optional[float] = Query(None, ge=0), 
    max_price: Optional[float] = Query(None, ge=0), 
    in_stock: Optional[bool] = Query(None)
):
    """Public catalog fetch with heavy filtering and pagination."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Querying Paginated Catalog (Page: {page})")
        
    items, total = await ProductService().get_products(page, page_size, category, search, min_price, max_price, in_stock)
    return paginate(items, total, page, page_size)

@router.get("/{slug}", status_code=status.HTTP_200_OK)
async def get_product(request: Request, slug: str):
    """Fetch complete product metadata by SEO-friendly slug."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Targeting Product fetch for slug -> '{slug}'")
        
    return success_response(await ProductService().get_product(slug))

@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission(ProductPermissions.CREATE))])
async def create_product(request: Request, payload: ProductCreate):
    """PBAC Guarded: Insert a new product into the catalog."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin inserting new product -> SKU: {payload.sku or 'Auto'}")
        
    result = await ProductService().create_product(payload.model_dump())
    return success_response(data=result, message=ProductMessages.PRODUCT_CREATED)

@router.patch("/{product_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def update_product(request: Request, product_id: uuid.UUID, payload: ProductUpdate):
    """PBAC Guarded: Update partial product metadata."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin overriding Product metadata -> ID: {str(product_id)[:8]}...")
        
    result = await ProductService().update_product(str(product_id), payload.model_dump(exclude_unset=True))
    return success_response(data=result, message=ProductMessages.PRODUCT_UPDATED)

@router.delete("/{product_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.DELETE))])
async def delete_product(request: Request, product_id: uuid.UUID):
    """PBAC Guarded: Soft deletes a product (hides from catalog)."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin isolating Product -> ID: {str(product_id)[:8]}...")
        
    await ProductService().delete_product(str(product_id))
    return success_response(message=ProductMessages.PRODUCT_DELETED)

@router.post("/{product_id}/images", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def upload_image_endpoint(request: Request, product_id: uuid.UUID, file: UploadFile = File(...)):
    """PBAC Guarded: Uploads product image asset (ABAC enforces max limit)."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Receiving asset upload for Product: {str(product_id)[:8]}...")
        
    return success_response(await ProductService().upload_image(str(product_id), await file.read(), file.filename or "unknown"))

@router.delete("/{product_id}/images/{index}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def delete_image_endpoint(request: Request, product_id: uuid.UUID, index: int):
    """PBAC Guarded: Removes image by index array."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Admin deleting Image Index [{index}] for Product: {str(product_id)[:8]}...")
        
    return success_response(await ProductService().delete_image(str(product_id), index))

@router.put("/{product_id}/images/reorder", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def reorder_images(request: Request, product_id: uuid.UUID, ordered_urls: List[str]):
    """PBAC Guarded: Rewrites image array sequence (ABAC enforces URL integrity)."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Restructuring image carousel for Product: {str(product_id)[:8]}...")
        
    return success_response(await ProductService().reorder_images(str(product_id), ordered_urls))