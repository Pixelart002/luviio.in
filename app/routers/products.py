"""
Products Router — Production Grade
===================================
- Products CRUD with soft delete
- Categories CRUD
- Image upload with WebP optimization
- Slug uniqueness guaranteed
- Security: admin-only mutations, magic byte validation
- All DELETE endpoints return 200 (FastAPI safe)

Features:
  • Server-side image processing (PIL → WebP)
  • Magic byte validation (content-type spoof protection)
  • Automatic slug deduplication
  • Atomic image reordering
  • Soft delete (is_active=False)
  • Bulletproof Search (ilike fallback)
  • FIXED: PostgREST 406 Errors via strict limit(1)
  • FIXED: Memory leaks on exact counts
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

from app.dependencies import require_admin
from app.supabase_client import get_admin_supabase

Image.MAX_IMAGE_PIXELS = 10_000_000
logger = logging.getLogger(__name__)
router = APIRouter(tags=["Products"])

# ── Constants ─────────────────────────────────────────────────────────────────
_MAX_IMAGES     = 10
_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
_THUMB_SIZE     = (800, 800)
_WEBP_QUALITY   = 80
_STORAGE_BUCKET = "product-images"

_IMAGE_MAGIC: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG":      "png",
    b"GIF8":         "gif",
    b"RIFF":         "webp",
}

# ── Schemas ───────────────────────────────────────────────────────────────────

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
    images: list[str] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
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
    images: list[str] | None = None
    category_id: str | None = None
    is_active: bool | None = None
    weight_grams: int | None = None

    @model_validator(mode="after")
    def compare_must_exceed_price(self):
        if self.compare_price and self.price and self.compare_price <= self.price:
            raise ValueError("compare_price must be greater than price")
        return self


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_real_image(data: bytes) -> bool:
    """Magic byte check — rejects spoofed content-types"""
    return any(data.startswith(magic) for magic in _IMAGE_MAGIC)


def _generate_unique_slug(sb: Any, base_slug: str) -> str:
    """Append -2, -3… until slug is unique"""
    slug, counter = base_slug, 2
    while True:
        # [FIX] Limit to 1 to save memory during check
        existing = sb.table("products").select("id").eq("slug", slug).limit(1).execute()
        if not getattr(existing, "data", None):
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def _upload_webp(sb: Any, file_bytes: bytes, product_id: str, img_hex: str) -> str:
    """Process → WebP → upload → return public URL"""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = img.convert("RGB")
        img.thumbnail(_THUMB_SIZE)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=_WEBP_QUALITY)
        optimized = buf.getvalue()
    except Exception:
        raise HTTPException(400, "Invalid image — must be JPEG/PNG/WebP")

    path = f"products/{product_id}/{img_hex}.webp"
    try:
        sb.storage.from_(_STORAGE_BUCKET).upload(
            path, optimized, {"content-type": "image/webp", "upsert": "true"}
        )
        return sb.storage.from_(_STORAGE_BUCKET).get_public_url(path).rstrip("?")
    except Exception as exc:
        logger.error("Storage upload failed | %s", exc)
        raise HTTPException(500, "Failed to upload image")


def _delete_storage_file(sb: Any, url: str) -> None:
    """Delete file from Supabase Storage by URL"""
    try:
        marker = f"/object/public/{_STORAGE_BUCKET}/"
        if marker in url:
            path = url.split(marker, 1)[1].split("?")[0]
            sb.storage.from_(_STORAGE_BUCKET).remove([path])
    except Exception as exc:
        logger.warning("Storage delete failed: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/categories")
def list_categories() -> list[dict[str, Any]]:
    """Public — list active categories"""
    sb = get_admin_supabase()
    res = sb.table("categories").select("*").eq("is_active", True).execute()
    return getattr(res, "data", None) or []


@router.post("/categories", status_code=201, dependencies=[Depends(require_admin)])
def create_category(payload: CategoryCreate) -> dict[str, Any]:
    """Admin — create category"""
    sb = get_admin_supabase()
    res = sb.table("categories").insert(payload.model_dump()).execute()
    if not getattr(res, "data", None):
        raise HTTPException(500, "Failed to create category")
    return res.data[0]


@router.delete("/categories/{category_id}", dependencies=[Depends(require_admin)])
def delete_category(category_id: uuid.UUID) -> dict[str, str]:
    """Admin — soft delete category (200 OK for FastAPI safety)"""
    sb = get_admin_supabase()
    
    # [FIX] Added limit(1) to avoid memory leak downloading all product IDs
    active = (
        sb.table("products").select("id", count="exact")
        .eq("category_id", str(category_id)).eq("is_active", True)
        .limit(1).execute()
    )
    if (active.count or 0) > 0:
        raise HTTPException(409, "Cannot delete — category has active products")
        
    sb.table("categories").update({"is_active": False}).eq("id", str(category_id)).execute()
    return {"message": "Category deleted"}


# ══════════════════════════════════════════════════════════════════════════════
#  PRODUCTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/products")
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    search: str | None = Query(None),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    in_stock: bool | None = None,
) -> dict[str, Any]:
    """Public — list products with filters"""
    sb = get_admin_supabase()
    q = (
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
        # [FIX] PostgREST 406 safety
        cat = sb.table("categories").select("id").eq("slug", category).limit(1).execute()
        if cat and getattr(cat, "data", None):
            q = q.eq("category_id", cat.data[0]["id"])
        else:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 0}

    if search:
        # [FIX] Safe fallback that prevents execution crashes if FTS is missing
        q = q.ilike("name", f"%{search}%")

    if min_price is not None: q = q.gte("price", min_price)
    if max_price is not None: q = q.lte("price", max_price)
    if in_stock: q = q.gt("stock", 0)

    offset = (page - 1) * page_size
    result = q.range(offset, offset + page_size - 1).execute()
    total = result.count or 0

    return {
        "items": getattr(result, "data", None) or [],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": -(-total // page_size) if page_size > 0 else 0,
    }


@router.get("/products/{slug}")
def get_product(slug: str) -> dict[str, Any]:
    """Public — get single product by slug"""
    sb = get_admin_supabase()
    
    # [FIX] PostgREST 406 safety (limit 1 instead of maybe_single)
    result = (
        sb.table("products")
        .select("*, categories(name, slug)")
        .eq("slug", slug).eq("is_active", True)
        .limit(1).execute()
    )
    if not result or not getattr(result, "data", None):
        raise HTTPException(404, "Product not found")

    product = result.data[0]
    product["images"] = product.get("images") or []
    return product


@router.post("/products", status_code=201, dependencies=[Depends(require_admin)])
def create_product(payload: ProductCreate) -> dict[str, Any]:
    """Admin — create product"""
    sb = get_admin_supabase()

    if payload.sku:
        # [FIX] Added limit(1) to save memory
        existing = sb.table("products").select("id").eq("sku", payload.sku).limit(1).execute()
        if getattr(existing, "data", None):
            raise HTTPException(409, f"SKU '{payload.sku}' already exists")

    data = payload.model_dump()
    data["slug"] = _generate_unique_slug(sb, data["slug"])
    data["price"] = float(data["price"])
    if data.get("compare_price"):
        data["compare_price"] = float(data["compare_price"])
    data["images"] = data.get("images") or []

    res = sb.table("products").insert(data).execute()
    if not getattr(res, "data", None):
        raise HTTPException(500, "Failed to create product")

    return res.data[0]


@router.patch("/products/{product_id}", dependencies=[Depends(require_admin)])
def update_product(product_id: uuid.UUID, payload: ProductUpdate) -> dict[str, Any]:
    """Admin — update product"""
    sb = get_admin_supabase()
    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}

    if "price" in data and data["price"]:
        data["price"] = float(data["price"])
    if "compare_price" in data and data["compare_price"]:
        data["compare_price"] = float(data["compare_price"])
    if "images" in data:
        imgs = data["images"] or []
        data["images"] = imgs
        data["image_url"] = imgs[0] if imgs else None

    result = sb.table("products").update(data).eq("id", str(product_id)).execute()
    if not getattr(result, "data", None):
        raise HTTPException(404, "Product not found")
    return result.data[0]


@router.delete("/products/{product_id}", dependencies=[Depends(require_admin)])
def delete_product(product_id: uuid.UUID) -> dict[str, str]:
    """Admin — soft delete product (200 OK for FastAPI safety)"""
    sb = get_admin_supabase()
    result = sb.table("products").update({"is_active": False}).eq("id", str(product_id)).execute()
    if not getattr(result, "data", None):
        raise HTTPException(404, "Product not found")
    return {"message": "Product deleted"}


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGES
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/products/{product_id}/images", dependencies=[Depends(require_admin)])
async def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Admin — upload single image (WebP optimized)"""
    sb = get_admin_supabase()
    pid = str(product_id)

    prod = sb.table("products").select("id, images").eq("id", pid).limit(1).execute()
    if not getattr(prod, "data", None):
        raise HTTPException(404, "Product not found")

    existing = prod.data[0].get("images") or []
    if len(existing) >= _MAX_IMAGES:
        raise HTTPException(400, f"Max {_MAX_IMAGES} images allowed")

    contents = await file.read()
    if len(contents) > _MAX_FILE_BYTES:
        raise HTTPException(400, f"File exceeds 5 MB limit")
    if not _is_real_image(contents):
        raise HTTPException(400, "Invalid image format")

    url = _upload_webp(sb, contents, pid, uuid.uuid4().hex[:12])
    all_images = existing + [url]

    sb.table("products").update({
        "images": all_images, "image_url": all_images[0]
    }).eq("id", pid).execute()

    return {"images": all_images, "image_url": all_images[0], "uploaded_url": url}


@router.delete("/products/{product_id}/images/{index}", dependencies=[Depends(require_admin)])
def delete_product_image(product_id: uuid.UUID, index: int) -> dict[str, Any]:
    """Admin — delete image by index"""
    sb = get_admin_supabase()
    pid = str(product_id)

    prod = sb.table("products").select("id, images").eq("id", pid).limit(1).execute()
    if not getattr(prod, "data", None):
        raise HTTPException(404, "Product not found")

    images = prod.data[0].get("images") or []
    if index < 0 or index >= len(images):
        raise HTTPException(400, f"Index {index} out of range (0-{len(images)-1})")

    deleted_url = images.pop(index)
    new_primary = images[0] if images else None

    sb.table("products").update({
        "images": images, "image_url": new_primary
    }).eq("id", pid).execute()

    _delete_storage_file(sb, deleted_url)
    return {"images": images, "image_url": new_primary, "deleted_url": deleted_url}


@router.put("/products/{product_id}/images/reorder", dependencies=[Depends(require_admin)])
def reorder_images(product_id: uuid.UUID, ordered_urls: list[str]) -> dict[str, Any]:
    """Admin — reorder images"""
    sb = get_admin_supabase()
    pid = str(product_id)

    prod = sb.table("products").select("id, images").eq("id", pid).limit(1).execute()
    if not getattr(prod, "data", None):
        raise HTTPException(404, "Product not found")

    current = prod.data[0].get("images") or []
    if set(ordered_urls) != set(current):
        raise HTTPException(400, "URLs must match existing images exactly")

    new_primary = ordered_urls[0] if ordered_urls else None
    sb.table("products").update({
        "images": ordered_urls, "image_url": new_primary
    }).eq("id", pid).execute()

    return {"images": ordered_urls, "image_url": new_primary}
