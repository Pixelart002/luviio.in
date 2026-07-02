import uuid
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from app.core.dependencies import require_permission
from app.permissions.products import ProductPermissions
from app.services.products.service import ProductService
from app.api.schemas.product_dto import CategoryCreate, ProductCreate, ProductUpdate
from app.utils.response import success_response
from app.utils.pagination import paginate

router = APIRouter(tags=["Products"])
service = ProductService()

@router.get("/categories")
async def list_categories(request: Request):
    if hasattr(request.state, "actions"): request.state.actions.append("Fetching active product categories from Global Catalog")
    return success_response(await service.get_categories())

@router.post("/categories", status_code=201, dependencies=[Depends(require_permission(ProductPermissions.CREATE))])
async def create_category(request: Request, payload: CategoryCreate):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin creating new category -> '{payload.name}'")
    return success_response(await service.create_category(payload.model_dump()))

@router.delete("/categories/{category_id}", dependencies=[Depends(require_permission(ProductPermissions.DELETE))])
async def delete_category(request: Request, category_id: uuid.UUID):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin initiating deletion for Category: {str(category_id)[:8]}...")
    await service.delete_category(str(category_id))
    return success_response(message="Category deleted")

@router.get("/products")
async def list_products(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), category: str = None, search: str = None, min_price: float = None, max_price: float = None, in_stock: bool = None):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Querying Paginated Catalog (Page: {page})")
    items, total = await service.get_products(page, page_size, category, search, min_price, max_price, in_stock)
    return paginate(items, total, page, page_size)

@router.get("/products/{slug}")
async def get_product(request: Request, slug: str):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Targeting Product fetch for slug -> '{slug}'")
    return success_response(await service.get_product(slug))

@router.post("/products", status_code=201, dependencies=[Depends(require_permission(ProductPermissions.CREATE))])
async def create_product(request: Request, payload: ProductCreate):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin inserting new product -> SKU: {payload.sku or 'Auto'}")
    return success_response(await service.create_product(payload.model_dump()))

@router.patch("/products/{product_id}", dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def update_product(request: Request, product_id: uuid.UUID, payload: ProductUpdate):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin overriding Product metadata -> ID: {str(product_id)[:8]}...")
    return success_response(await service.update_product(str(product_id), payload.model_dump(exclude_unset=True)))

@router.delete("/products/{product_id}", dependencies=[Depends(require_permission(ProductPermissions.DELETE))])
async def delete_product(request: Request, product_id: uuid.UUID):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin isolating Product -> ID: {str(product_id)[:8]}...")
    await service.delete_product(str(product_id))
    return success_response(message="Product deleted")

@router.post("/products/{product_id}/images", dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def upload_image_endpoint(request: Request, product_id: uuid.UUID, file: UploadFile = File(...)):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Receiving asset upload for Product: {str(product_id)[:8]}...")
    return success_response(await service.upload_image(str(product_id), await file.read(), file.filename or "unknown"))

@router.delete("/products/{product_id}/images/{index}", dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def delete_image_endpoint(request: Request, product_id: uuid.UUID, index: int):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin deleting Image Index [{index}] for Product: {str(product_id)[:8]}...")
    return success_response(await service.delete_image(str(product_id), index))

@router.put("/products/{product_id}/images/reorder", dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def reorder_images(request: Request, product_id: uuid.UUID, ordered_urls: list[str]):
    if hasattr(request.state, "actions"): request.state.actions.append(f"Restructuring image carousel for Product: {str(product_id)[:8]}...")
    return success_response(await service.reorder_images(str(product_id), ordered_urls))