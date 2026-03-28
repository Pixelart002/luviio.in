"""
Products Router
================
Changes from original:
  All .single() → .maybe_single() — no PGRST116 on missing rows.
  FIXED: Added robust NoneType checks for .data attributes to prevent crashes.
  ADDED: Auto unique slug generation — no more 409 conflicts on duplicate slugs.
         _generate_unique_slug() appends -2, -3... until a free slot is found.
"""
import io
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query, UploadFile, File
from PIL import Image
from pydantic import BaseModel, Field, model_validator

from postgrest.exceptions import APIError as PostgrestError

from app.dependencies import require_admin
from app.supabase_client import get_admin_supabase

Image.MAX_IMAGE_PIXELS = 10_000_000
logger = logging.getLogger(__name__)
router = APIRouter(tags=["Products"])

_IMAGE_MAGIC: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG":      "png",
    b"GIF8":         "gif",
    b"RIFF":         "webp",
}


def _is_real_image(data: bytes) -> bool:
    return any(data.startswith(magic) for magic in _IMAGE_MAGIC)


# ── Slug Helper ───────────────────────────────────────────────────────────────

def _generate_unique_slug(sb, base_slug: str) -> str:
    """
    Ensures the slug is unique in the products table.
    If 'premium-soap' exists → tries 'premium-soap-2', 'premium-soap-3', etc.
    Stops at first free slot.
    """
    slug = base_slug
    counter = 2
    while True:
        existing = sb.table("products").select("id").eq("slug", slug).execute()
        if not existing or not hasattr(existing, "data") or not existing.data:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


# ── Models ────────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(max_length=100)
    slug: str = Field(max_length=120, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    image_url: str | None = None


class ProductCreate(BaseModel):
    name: str = Field(max_length=255)
    slug: str = Field(max_length=280, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    short_description: str | None = None
    sku: str | None = Field(default=None, max_length=100)
    category_id: str | None = None
    price: Decimal = Field(gt=0, decimal_places=2)
    compare_price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    stock: int = Field(ge=0, default=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    weight_grams: int | None = Field(default=None, ge=0)
    image_url: str | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def compare_must_exceed_price(self) -> "ProductCreate":
        if self.compare_price and self.price:
            if self.compare_price <= self.price:
                raise ValueError("compare_price must be greater than price")
        return self


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    short_description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    compare_price: Decimal | None = None
    stock: int | None = Field(default=None, ge=0)
    low_stock_threshold: int | None = None
    image_url: str | None = None
    category_id: str | None = None
    is_active: bool | None = None
    weight_grams: int | None = None

    @model_validator(mode="after")
    def compare_must_exceed_price(self) -> "ProductUpdate":
        if self.compare_price and self.price:
            if self.compare_price <= self.price:
                raise ValueError("compare_price must be greater than price")
        return self


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories")
def list_categories() -> list[dict[str, Any]]:
    sb = get_admin_supabase()
    res = sb.table("categories").select("*").eq("is_active", True).execute()
    return res.data if res and hasattr(res, "data") and res.data else []


@router.post("/categories", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_category(payload: CategoryCreate) -> dict[str, Any]:
    sb = get_admin_supabase()
    res = sb.table("categories").insert(payload.model_dump()).execute()
    if not res or not hasattr(res, "data") or not res.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create category")
    return res.data[0]


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_category(category_id: UUID) -> None:
    sb = get_admin_supabase()
    active = (
        sb.table("products")
        .select("id", count="exact")
        .eq("category_id", str(category_id))
        .eq("is_active", True)
        .execute()
    )
    if active and hasattr(active, "count") and (active.count or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete — category has active products.",
        )
    sb.table("categories").update({"is_active": False}).eq("id", str(category_id)).execute()


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(default=None, max_length=120),
    search: str | None = Query(default=None, max_length=100),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    in_stock: bool | None = None,
) -> dict[str, Any]:
    sb = get_admin_supabase()
    q = (
        sb.table("products")
        .select(
            "id, name, slug, description, short_description, sku, category_id, "
            "price, compare_price, stock, low_stock_threshold, weight_grams, "
            "image_url, is_active, created_at, categories(name, slug)",
            count="exact",
        )
        .eq("is_active", True)
    )

    if category:
        try:
            cat = (
                sb.table("categories")
                .select("id")
                .eq("slug", category)
                .maybe_single()
                .execute()
            )
            if cat and hasattr(cat, "data") and cat.data:
                q = q.eq("category_id", cat.data["id"])
            else:
                return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 0}
        except Exception as e:
            logger.warning(f"Error fetching category {category}: {e}")

    if search:
        try:
            q = q.text_search("fts", search)
        except Exception as e:
            logger.warning("FTS search failed, falling back to ilike: %s", e)
            q = q.ilike("name", f"%{search}%")

    if min_price is not None:
        q = q.gte("price", min_price)
    if max_price is not None:
        q = q.lte("price", max_price)
    if in_stock:
        q = q.gt("stock", 0)

    offset = (page - 1) * page_size
    try:
        result = q.range(offset, offset + page_size - 1).execute()
        total: int = result.count if result and hasattr(result, "count") and result.count else 0
        items = result.data if result and hasattr(result, "data") and result.data else []
        return {
            "items":     items,
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "pages":     -(-total // page_size) if page_size > 0 else 0,
        }
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch products")


@router.get("/products/{slug}")
def get_product(slug: str) -> dict[str, Any]:
    sb = get_admin_supabase()
    result = (
        sb.table("products")
        .select("*, categories(name, slug), product_images(*)")
        .eq("slug", slug)
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    if not result or not hasattr(result, "data") or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return result.data


@router.post("/products", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_product(payload: ProductCreate) -> dict[str, Any]:
    sb = get_admin_supabase()

    # SKU uniqueness check (slug is handled by auto-generator below)
    if payload.sku:
        existing_sku = sb.table("products").select("id").eq("sku", payload.sku).execute()
        if existing_sku and hasattr(existing_sku, "data") and existing_sku.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product with SKU '{payload.sku}' already exists",
            )

    # Auto unique slug — no manual conflict handling needed
    unique_slug = _generate_unique_slug(sb, payload.slug)
    if unique_slug != payload.slug:
        logger.info("Slug '%s' taken — assigned '%s'", payload.slug, unique_slug)

    data = payload.model_dump()
    data["slug"] = unique_slug
    data["price"] = float(data["price"])
    if data.get("compare_price"):
        data["compare_price"] = float(data["compare_price"])

    res = sb.table("products").insert(data).execute()
    if not res or not hasattr(res, "data") or not res.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create product")

    created = res.data[0]
    if unique_slug != payload.slug:
        # Inform admin the slug was changed
        created["_slug_note"] = f"Slug '{payload.slug}' was taken — assigned '{unique_slug}'"

    return created


@router.patch("/products/{product_id}", dependencies=[Depends(require_admin)])
def update_product(product_id: UUID, payload: ProductUpdate) -> dict[str, Any]:
    sb = get_admin_supabase()
    data: dict[str, Any] = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if "price" in data and data["price"]:
        data["price"] = float(data["price"])
    if "compare_price" in data and data["compare_price"]:
        data["compare_price"] = float(data["compare_price"])

    result = sb.table("products").update(data).eq("id", str(product_id)).execute()

    if not result or not hasattr(result, "data") or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or no changes made")
    return result.data[0]


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_product(product_id: UUID) -> None:
    """
    Hard delete — product permanently remove hota hai.
    UUID free ho jaata hai, slug bhi reusable ho jaata hai.
    Note: Supabase FK constraint hai order_items.product_id → products.id
    Agar product kisi active/paid order mein hai toh DB 409 throw karega — safe.
    """
    sb = get_admin_supabase()
    result = sb.table("products").delete().eq("id", str(product_id)).execute()
    if not result or not hasattr(result, "data") or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


@router.post("/products/{product_id}/image", dependencies=[Depends(require_admin)])
async def upload_product_image(
    product_id: UUID,
    file: UploadFile = File(...),
) -> dict[str, str]:
    contents: bytes = await file.read()

    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Max 5MB allowed")

    if not _is_real_image(contents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image. Only JPEG, PNG, GIF, WebP allowed.",
        )

    sb = get_admin_supabase()
    product = (
        sb.table("products")
        .select("id")
        .eq("id", str(product_id))
        .maybe_single()
        .execute()
    )

    if not product or not hasattr(product, "data") or not product.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    try:
        img = Image.open(io.BytesIO(contents))
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image dimensions too large. Max ~10 megapixels.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("PIL failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not process image")

    img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=80)
    optimized: bytes = buffer.getvalue()

    path = f"products/{product_id}.webp"
    try:
        sb.storage.from_("product-images").upload(
            path, optimized, {"content-type": "image/webp", "upsert": "true"}
        )
        url: str = sb.storage.from_("product-images").get_public_url(path).rstrip("?")
        sb.table("products").update({"image_url": url}).eq("id", str(product_id)).execute()
    except Exception as e:
        logger.error(f"Image upload to Supabase failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save image")

    logger.info("Image uploaded: product=%s path=%s", product_id, path)
    return {"image_url": url}