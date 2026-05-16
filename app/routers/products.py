"""
Products Router
===============
Fixes applied vs previous version:
BUG 1-6: All previous logic and image upload bug fixes retained.
BUG 7 (CRASH FIX): Changed all DELETE endpoints from 204 No Content to 200 OK.
  FastAPI strictly asserts that 204 routes cannot have any response model.
  Returning 200 OK with a JSON message is safer, prevents startup crashes, 
  and is much easier for the frontend to parse.
"""
from __future__ import annotations

import io
import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from PIL import Image
from pydantic import BaseModel, Field, model_validator

from postgrest.exceptions import APIError as PostgrestError

from app.dependencies import require_admin
from app.supabase_client import get_admin_supabase

# PIL safety limit
Image.MAX_IMAGE_PIXELS = 10_000_000
logger = logging.getLogger(__name__)
router = APIRouter(tags=["Products"])

# ── Image constants ───────────────────────────────────────────────────────────
_MAX_IMAGES      = 10
_MAX_FILE_BYTES  = 5 * 1024 * 1024          # 5 MB per file
_THUMB_SIZE      = (800, 800)
_WEBP_QUALITY    = 80
_STORAGE_BUCKET  = "product-images"

# Magic bytes for supported formats (content-type spoof protection)
_IMAGE_MAGIC: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG":      "png",
    b"GIF8":         "gif",
    b"RIFF":         "webp",
}


# ── Private helpers ───────────────────────────────────────────────────────────

def _is_real_image(data: bytes) -> bool:
    """Magic-bytes check — rejects files that lie about their content-type."""
    return any(data.startswith(magic) for magic in _IMAGE_MAGIC)


def _generate_unique_slug(sb: Any, base_slug: str) -> str:
    """Append -2, -3 … until slug is unique."""
    slug    = base_slug
    counter = 2
    while True:
        existing = sb.table("products").select("id").eq("slug", slug).execute()
        if not getattr(existing, "data", None):
            return slug
        slug    = f"{base_slug}-{counter}"
        counter += 1


def _upload_webp(sb: Any, file_bytes: bytes, product_id: str, img_hex: str) -> str:
    """
    Process raw image bytes → resize → WebP → upload to Storage.
    All images use the same path pattern: products/{product_id}/{hex}.webp
    Returns the public URL.
    Raises HTTPException on processing or upload failure.
    """
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image dimensions too large",
            )
        img = img.convert("RGB")
        img.thumbnail(_THUMB_SIZE)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=_WEBP_QUALITY)
        optimized = buf.getvalue()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("PIL processing failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not process image — ensure file is a valid JPEG/PNG/WebP",
        )

    path = f"products/{product_id}/{img_hex}.webp"
    try:
        sb.storage.from_(_STORAGE_BUCKET).upload(
            path, optimized,
            {"content-type": "image/webp", "upsert": "true"},
        )
        url: str = sb.storage.from_(_STORAGE_BUCKET).get_public_url(path)
        return url.rstrip("?")
    except Exception as exc:
        logger.error("Storage upload failed | path=%s | %s", path, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload image to cloud storage",
        )


def _delete_storage_file(sb: Any, url: str) -> None:
    """
    Extract the storage path from a public URL and delete the file.
    """
    try:
        marker = f"/object/public/{_STORAGE_BUCKET}/"
        if marker in url:
            path = url.split(marker, 1)[1].split("?")[0]
            sb.storage.from_(_STORAGE_BUCKET).remove([path])
            logger.info("Deleted storage file: %s", path)
    except Exception as exc:
        logger.warning("Storage file deletion failed | url=%s | %s", url[:60], exc)


# ══════════════════════════════════════════════════════════════════════════════
#  SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class CategoryCreate(BaseModel):
    name:        str       = Field(max_length=100)
    slug:        str       = Field(max_length=120, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    image_url:   str | None = None


class ProductCreate(BaseModel):
    name:               str            = Field(max_length=255)
    slug:               str            = Field(max_length=280, pattern=r"^[a-z0-9-]+$")
    description:        str | None     = None
    short_description:  str | None     = None
    sku:                str | None     = Field(default=None, max_length=100)
    category_id:        str | None     = None
    price:              Decimal        = Field(gt=0, decimal_places=2)
    compare_price:      Decimal | None = Field(default=None, gt=0, decimal_places=2)
    stock:              int            = Field(ge=0, default=0)
    low_stock_threshold: int           = Field(default=10, ge=0)
    weight_grams:       int | None     = Field(default=None, ge=0)
    image_url:          str | None     = None
    images:             list[str]      = Field(default_factory=list)
    is_active:          bool           = True

    @model_validator(mode="after")
    def compare_must_exceed_price(self) -> "ProductCreate":
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError("compare_price must be greater than price")
        return self


class ProductUpdate(BaseModel):
    name:               str | None     = None
    description:        str | None     = None
    short_description:  str | None     = None
    price:              Decimal | None = Field(default=None, gt=0)
    compare_price:      Decimal | None = None
    stock:              int | None     = Field(default=None, ge=0)
    low_stock_threshold: int | None   = None
    image_url:          str | None     = None
    images:             list[str] | None = None
    category_id:        str | None     = None
    is_active:          bool | None    = None
    weight_grams:       int | None     = None

    @model_validator(mode="after")
    def compare_must_exceed_price(self) -> "ProductUpdate":
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError("compare_price must be greater than price")
        return self


# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/categories")
def list_categories() -> list[dict[str, Any]]:
    sb  = get_admin_supabase()
    res = sb.table("categories").select("*").eq("is_active", True).execute()
    return getattr(res, "data", None) or []


@router.post("/categories", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
def create_category(payload: CategoryCreate) -> dict[str, Any]:
    sb  = get_admin_supabase()
    res = sb.table("categories").insert(payload.model_dump()).execute()
    if not getattr(res, "data", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create category",
        )
    return res.data[0]


@router.delete("/categories/{category_id}", status_code=status.HTTP_200_OK,
               dependencies=[Depends(require_admin)])
def delete_category(category_id: uuid.UUID) -> dict[str, Any]:
    """Changed from 204 to 200 OK to prevent FastAPI assertion errors"""
    sb     = get_admin_supabase()
    active = (
        sb.table("products")
        .select("id", count="exact")
        .eq("category_id", str(category_id))
        .eq("is_active", True)
        .execute()
    )
    if (active.count or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete — category has active products.",
        )
    sb.table("categories").update({"is_active": False}).eq("id", str(category_id)).execute()
    return {"message": "Category deleted successfully"}


# ══════════════════════════════════════════════════════════════════════════════
#  PRODUCT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/products")
def list_products(
    page:       int   = Query(1, ge=1),
    page_size:  int   = Query(20, ge=1, le=100),
    category:   str | None = Query(default=None, max_length=120),
    search:     str | None = Query(default=None, max_length=100),
    min_price:  float | None = Query(default=None, ge=0),
    max_price:  float | None = Query(default=None, ge=0),
    in_stock:   bool | None  = None,
) -> dict[str, Any]:
    sb = get_admin_supabase()
    q  = (
        sb.table("products")
        .select(
            "id, name, slug, short_description, sku, category_id, "
            "price, compare_price, stock, low_stock_threshold, weight_grams, "
            "image_url, images, is_active, created_at, categories(name, slug)",
            count="exact",
        )
        .eq("is_active", True)
    )

    if category:
        try:
            cat = sb.table("categories").select("id").eq("slug", category).maybe_single().execute()
            if cat and getattr(cat, "data", None):
                q = q.eq("category_id", cat.data["id"])
            else:
                return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 0}
        except Exception as exc:
            logger.warning("Category filter error for '%s': %s", category, exc)

    if search:
        try:
            q = q.text_search("fts", search)
        except Exception:
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
        total  = result.count or 0
        items  = getattr(result, "data", None) or []
        return {
            "items":     items,
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "pages":     -(-total // page_size) if page_size > 0 else 0,
        }
    except Exception as exc:
        logger.error("list_products failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products",
        )


@router.get("/products/{slug}")
def get_product(slug: str) -> dict[str, Any]:
    sb     = get_admin_supabase()
    result = (
        sb.table("products")
        .select("*, categories(name, slug)")
        .eq("slug", slug)
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    if not result or not getattr(result, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = result.data
    if product.get("images") is None:
        product["images"] = []

    return product


@router.post("/products", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
def create_product(payload: ProductCreate) -> dict[str, Any]:
    sb = get_admin_supabase()

    if payload.sku:
        existing = sb.table("products").select("id").eq("sku", payload.sku).execute()
        if getattr(existing, "data", None):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product with SKU '{payload.sku}' already exists",
            )

    unique_slug = _generate_unique_slug(sb, payload.slug)
    data        = payload.model_dump()
    data["slug"]  = unique_slug
    data["price"] = float(data["price"])
    if data.get("compare_price"):
        data["compare_price"] = float(data["compare_price"])
    data["images"] = data.get("images") or []

    res = sb.table("products").insert(data).execute()
    if not getattr(res, "data", None):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product",
        )

    created = res.data[0]
    if unique_slug != payload.slug:
        created["_slug_note"] = f"Slug '{payload.slug}' was taken — assigned '{unique_slug}'"
    return created


@router.patch("/products/{product_id}", dependencies=[Depends(require_admin)])
def update_product(product_id: uuid.UUID, payload: ProductUpdate) -> dict[str, Any]:
    sb   = get_admin_supabase()
    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}

    if "price" in data and data["price"]:
        data["price"] = float(data["price"])
    if "compare_price" in data and data["compare_price"]:
        data["compare_price"] = float(data["compare_price"])

    if "images" in data:
        imgs = data["images"] or []
        data["images"] = imgs
        if imgs and "image_url" not in data:
            data["image_url"] = imgs[0]
        elif not imgs:
            data["image_url"] = None

    result = sb.table("products").update(data).eq("id", str(product_id)).execute()
    if not getattr(result, "data", None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or no changes made",
        )
    return result.data[0]


@router.delete("/products/{product_id}", status_code=status.HTTP_200_OK,
               dependencies=[Depends(require_admin)])
def delete_product(product_id: uuid.UUID) -> dict[str, Any]:
    """Changed from 204 to 200 OK to prevent FastAPI assertion errors"""
    sb     = get_admin_supabase()
    result = sb.table("products").update({"is_active": False}).eq("id", str(product_id)).execute()
    if not getattr(result, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    
    return {"message": "Product deleted successfully"}


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE ENDPOINTS 
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/products/{product_id}/images", dependencies=[Depends(require_admin)])
async def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    sb  = get_admin_supabase()
    pid = str(product_id)

    prod_res = (
        sb.table("products")
        .select("id, images, image_url")
        .eq("id", pid)
        .limit(1)
        .execute()
    )
    if not getattr(prod_res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    existing_images: list[str] = prod_res.data[0].get("images") or []

    if len(existing_images) >= _MAX_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot upload image — already have {len(existing_images)}. Maximum is {_MAX_IMAGES} total.",
        )

    contents: bytes = await file.read()

    if len(contents) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{file.filename}' exceeds 5 MB limit",
        )
    if not _is_real_image(contents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{file.filename}' is not a valid image (JPEG/PNG/WebP/GIF)",
        )

    img_hex = uuid.uuid4().hex[:12]
    url     = _upload_webp(sb, contents, pid, img_hex)
    logger.info("Image uploaded | product=%.8s url=%s", pid, url[:60])

    all_images = existing_images + [url]

    update_data: dict[str, Any] = {
        "images":    all_images,
        "image_url": all_images[0],
    }
    sb.table("products").update(update_data).eq("id", pid).execute()

    return {
        "message":       "Image uploaded successfully",
        "total_count":   len(all_images),
        "images":        all_images,
        "image_url":     all_images[0],
        "uploaded_url":  url
    }


@router.delete("/products/{product_id}/images/{index}", status_code=status.HTTP_200_OK,
               dependencies=[Depends(require_admin)])
def delete_product_image(
    product_id: uuid.UUID,
    index:      int,
) -> dict[str, Any]:
    sb  = get_admin_supabase()
    pid = str(product_id)

    prod_res = (
        sb.table("products")
        .select("id, images, image_url")
        .eq("id", pid)
        .limit(1)
        .execute()
    )
    if not getattr(prod_res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    current_images: list[str] = prod_res.data[0].get("images") or []

    if not current_images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product has no images to delete",
        )
    if index < 0 or index >= len(current_images):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Index {index} out of range — product has {len(current_images)} image(s) (0-based)",
        )

    deleted_url    = current_images.pop(index)
    new_image_url  = current_images[0] if current_images else None

    sb.table("products").update({
        "images":    current_images,
        "image_url": new_image_url,
    }).eq("id", pid).execute()

    _delete_storage_file(sb, deleted_url)

    logger.info(
        "Image deleted | product=%.8s index=%d remaining=%d",
        pid, index, len(current_images),
    )

    return {
        "message":       "Image deleted successfully",
        "deleted_url":   deleted_url,
        "remaining":     len(current_images),
        "images":        current_images,
        "image_url":     new_image_url,
    }


@router.put("/products/{product_id}/images/reorder",
            dependencies=[Depends(require_admin)])
def reorder_product_images(
    product_id: uuid.UUID,
    ordered_urls: list[str],
) -> dict[str, Any]:
    sb  = get_admin_supabase()
    pid = str(product_id)

    prod_res = (
        sb.table("products")
        .select("id, images")
        .eq("id", pid)
        .limit(1)
        .execute()
    )
    if not getattr(prod_res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    current_images: list[str] = prod_res.data[0].get("images") or []

    if set(ordered_urls) != set(current_images):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provided URLs must match existing product images exactly — no additions or removals allowed",
        )

    new_primary = ordered_urls[0] if ordered_urls else None
    sb.table("products").update({
        "images":    ordered_urls,
        "image_url": new_primary,
    }).eq("id", pid).execute()

    return {
        "message":   "Images reordered successfully",
        "images":    ordered_urls,
        "image_url": new_primary,
    }
