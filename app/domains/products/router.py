"""Product Domain Router — canonical HTTP boundary."""
import json
import logging
import uuid
from html import escape
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.constants.product_messages import ProductMessages
from app.core.dependencies import require_permission
from app.core.logging_config import request_id_ctx
from app.domains.products.schemas import CategoryCreate, ProductCreate, ProductUpdate
from app.domains.products.service import ProductService
from app.domains.products.taxonomy import gst_rates, lookup_hsn, search_hsn
from app.permissions.products import ProductPermissions
from app.utils.pagination import paginate
from app.utils.response import success_response

router = APIRouter(tags=["Products"])
logger = logging.getLogger(__name__)


def _validation_error(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors(include_url=False))


@router.get("/categories", status_code=status.HTTP_200_OK)
async def list_categories(request: Request) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Fetching active product categories from Global Catalog")
    return success_response(data=await ProductService().get_categories())


@router.post("/categories", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission(ProductPermissions.CREATE))])
async def create_category(request: Request, payload: CategoryCreate) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin creating new category -> '{payload.name}'")
    result = await ProductService().create_category(payload.model_dump())
    return success_response(data=result, message=ProductMessages.CATEGORY_CREATED)


@router.delete("/categories/{category_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.DELETE))])
async def delete_category(request: Request, category_id: uuid.UUID) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin initiating deletion for Category: {str(category_id)[:8]}...")
    await ProductService().delete_category(str(category_id))
    return success_response(message=ProductMessages.CATEGORY_DELETED)


@router.get("/products/measurements", status_code=status.HTTP_200_OK)
async def measurement_catalog(request: Request) -> Dict[str, Any]:
    return success_response(data=await ProductService().get_measurement_catalog())


@router.get("/products", status_code=status.HTTP_200_OK)
async def list_products(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), category: str = Query(None), search: str = Query(None), min_price: float = Query(None), max_price: float = Query(None), in_stock: bool = Query(None)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Querying Paginated Catalog (Page: {page})")
    items, total = await ProductService().get_products(page, page_size, category, search, min_price, max_price, in_stock)
    return paginate(items, total, page, page_size)


@router.get("/products/taxonomy/hsn-search", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.READ))])
async def hsn_search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(8, ge=1, le=20),
) -> Dict[str, Any]:
    """Return live HSN candidates and their provider-supplied GST rates for admin product entry."""
    results = await search_hsn(q, limit)
    rates = gst_rates(results)
    return success_response(
        data={
            "query": q,
            "results": results,
            "gst_rates": rates,
            "recommended_gst_rate": rates[0] if len(rates) == 1 else None,
            "source": "external_taxonomy_provider",
        }
    )


@router.get("/products/taxonomy/hsn/{code}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.READ))])
async def hsn_lookup(request: Request, code: str) -> Dict[str, Any]:
    """Return live HSN details/rates without a local hardcoded HSN table."""
    results = await lookup_hsn(code)
    rates = gst_rates(results)
    return success_response(
        data={
            "code": code,
            "results": results,
            "gst_rates": rates,
            "recommended_gst_rate": rates[0] if len(rates) == 1 else None,
            "source": "external_taxonomy_provider",
        }
    )


@router.get("/products/share/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def product_share_page(request: Request, slug: str) -> HTMLResponse:
    """Server-rendered share shell for WhatsApp/Facebook/LinkedIn crawlers.

    Social crawlers do not execute the React application, so product OG metadata
    must be available in the initial HTML response.
    """
    product = await ProductService().get_product(slug)
    site_url = "https://luviio.in"
    product_slug = str(product.get("slug") or slug)
    canonical = f"{site_url}/product/{escape(product_slug, quote=True)}"
    title = escape(str(product.get("seo_title") or product.get("name") or "Luviio product"))
    description = escape(str(product.get("seo_description") or product.get("short_description") or product.get("description") or "Shop on Luviio."))
    image = str(product.get("image_url") or ((product.get("images") or [None])[0]) or "")
    if image.startswith("/"):
        image = site_url + image
    image = escape(image, quote=True)
    canonical_attr = escape(canonical, quote=True)
    redirect_url = escape(f"/product.html?slug={product_slug}", quote=True)
    html = f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{title}</title><meta name=\"description\" content=\"{description}\"><link rel=\"canonical\" href=\"{canonical_attr}\"><meta property=\"og:type\" content=\"product\"><meta property=\"og:site_name\" content=\"Luviio\"><meta property=\"og:title\" content=\"{title}\"><meta property=\"og:description\" content=\"{description}\"><meta property=\"og:url\" content=\"{canonical_attr}\"><meta property=\"og:image\" content=\"{image}\"><meta property=\"og:image:alt\" content=\"{title}\"><meta name=\"twitter:card\" content=\"summary_large_image\"><meta name=\"twitter:title\" content=\"{title}\"><meta name=\"twitter:description\" content=\"{description}\"><meta name=\"twitter:image\" content=\"{image}\"><meta http-equiv=\"refresh\" content=\"0;url={redirect_url}\"></head><body><p>Opening product…</p><script>location.replace({redirect_url!r})</script></body></html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=300, s-maxage=3600"})


@router.get("/products/{slug}", status_code=status.HTTP_200_OK)
async def get_product(request: Request, slug: str) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Targeting Product fetch for slug -> '{slug}'")
    return success_response(data=await ProductService().get_product(slug))


@router.post("/products", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission(ProductPermissions.CREATE))])
async def create_product(request: Request) -> Dict[str, Any]:
    """Create a product from JSON or multipart/form-data with optional image files."""
    content_type = request.headers.get("content-type", "").lower()
    request_id = request_id_ctx.get()
    logger.info("product.create.start request_id=%s content_type=%s", request_id, content_type.split(";", 1)[0])
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            raw_product = form.get("product")
            if not raw_product:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Missing product payload")
            try:
                payload = ProductCreate.model_validate(json.loads(str(raw_product)))
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Product payload must contain valid JSON") from exc
            except ValidationError as exc:
                raise _validation_error(exc)

            image_files: List[tuple[bytes, str]] = []
            for value in form.getlist("files"):
                if isinstance(value, UploadFile):
                    image_files.append((await value.read(), value.filename or "unknown"))
            logger.info("product.create.payload request_id=%s sku=%s images=%s", request_id, payload.sku or "Auto", len(image_files))
            result = await ProductService().create_product_with_images(payload.model_dump(mode="json"), image_files)
        else:
            try:
                payload = ProductCreate.model_validate(await request.json())
            except ValidationError as exc:
                raise _validation_error(exc)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Request body must contain valid JSON") from exc
            logger.info("product.create.payload request_id=%s sku=%s images=0", request_id, payload.sku or "Auto")
            result = await ProductService().create_product(payload.model_dump())
    except HTTPException as exc:
        logger.warning("product.create.http_error request_id=%s status=%s detail=%s", request_id, exc.status_code, str(exc.detail)[:300])
        raise
    except Exception as exc:
        logger.exception("product.create.error request_id=%s error=%s", request_id, str(exc)[:300])
        request.state.product_create_error = str(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to create product") from exc

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin inserting new product -> SKU: {payload.sku or 'Auto'}")
    product_id = result.get("id") if isinstance(result, dict) else None
    logger.info("product.create.success request_id=%s product_id=%s sku=%s", request_id, product_id or "-", payload.sku or "Auto")
    return success_response(data=result, message=ProductMessages.PRODUCT_CREATED)


@router.patch("/products/{product_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def update_product(request: Request, product_id: uuid.UUID, payload: ProductUpdate) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin overriding Product metadata -> ID: {str(product_id)[:8]}...")
    result = await ProductService().update_product(str(product_id), payload.model_dump(mode="json", exclude_unset=True))
    return success_response(data=result, message=ProductMessages.PRODUCT_UPDATED)


@router.delete("/products/{product_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.DELETE))])
async def delete_product(request: Request, product_id: uuid.UUID) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin isolating Product -> ID: {str(product_id)[:8]}...")
    await ProductService().delete_product(str(product_id))
    return success_response(message=ProductMessages.PRODUCT_DELETED)


@router.post("/products/{product_id}/images", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def upload_image_endpoint(request: Request, product_id: uuid.UUID) -> Dict[str, Any]:
    form = await request.form()
    image_files: List[tuple[bytes, str]] = []
    for value in form.getlist("files"):
        if isinstance(value, UploadFile):
            image_files.append((await value.read(), value.filename or "unknown"))
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Receiving {len(image_files)} asset upload(s) for Product: {str(product_id)[:8]}...")
    result = await ProductService().upload_images(str(product_id), image_files)
    return success_response(data=result, message=ProductMessages.IMAGE_UPLOADED)


@router.delete("/products/{product_id}/images/{index}", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def delete_image_endpoint(request: Request, product_id: uuid.UUID, index: int) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin deleting Image Index [{index}] for Product: {str(product_id)[:8]}...")
    result = await ProductService().delete_image(str(product_id), index)
    return success_response(data=result, message=ProductMessages.IMAGE_DELETED)


@router.put("/products/{product_id}/images/reorder", status_code=status.HTTP_200_OK, dependencies=[Depends(require_permission(ProductPermissions.UPDATE))])
async def reorder_images(request: Request, product_id: uuid.UUID, ordered_urls: List[str]) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Restructuring image carousel for Product: {str(product_id)[:8]}...")
    result = await ProductService().reorder_images(str(product_id), ordered_urls)
    return success_response(data=result, message=ProductMessages.IMAGES_REORDERED)
