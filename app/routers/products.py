import io
import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status, Depends, Query, UploadFile, File
from PIL import Image
from pydantic import BaseModel, Field

from app.dependencies import require_admin
from app.supabase_client import get_admin_supabase

# SECURITY: Decompression bomb protection — max 10MP (~40MB decompressed RAM)
Image.MAX_IMAGE_PIXELS = 10_000_000

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Products"])

# Magic bytes for real image validation (content-type spoof se protection)
_IMAGE_MAGIC: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG":      "png",
    b"GIF8":         "gif",
    b"RIFF":         "webp",
}


def _is_real_image(data: bytes) -> bool:
    """Client-provided Content-Type pe rely mat karo — actual bytes check karo."""
    return any(data.startswith(magic) for magic in _IMAGE_MAGIC)


# ── Request models ─────────────────────────────────────────────────────────────

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


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories")
def list_categories() -> list[dict[str, Any]]:
    sb = get_admin_supabase()
    result = sb.table("categories").select("*").eq("is_active", True).execute()
    return result.data


@router.post(
    "/categories",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_category(payload: CategoryCreate) -> dict[str, Any]:
    sb = get_admin_supabase()
    result = sb.table("categories").insert(payload.model_dump()).execute()
    return result.data[0]


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_category(category_id: str) -> None:
    sb = get_admin_supabase()

    # Active products check — orphan products prevent karo
    active_products = (
        sb.table("products")
        .select("id", count="exact")
        .eq("category_id", category_id)
        .eq("is_active", True)
        .execute()
    )
    if (active_products.count or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete category — it has active products. Reassign or deactivate them first.",
        )

    sb.table("categories").update({"is_active": False}).eq("id", category_id).execute()


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(default=None, max_length=120),
    search: str | None = Query(default=None, max_length=100),
    min_price: float | None = Query(default=None, ge=0),   # negative price nahi
    max_price: float | None = Query(default=None, ge=0),   # negative price nahi
    in_stock: bool | None = None,
) -> dict[str, Any]:
    sb = get_admin_supabase()
    q = (
        sb.table("products")
        .select("*, categories(name, slug)", count="exact")
        .eq("is_active", True)
    )

    if category:
        cat = sb.table("categories").select("id").eq("slug", category).single().execute()
        if cat.data:
            q = q.eq("category_id", cat.data["id"])

    if search:
        q = q.ilike("name", f"%{search}%")

    if min_price is not None:
        q = q.gte("price", min_price)

    if max_price is not None:
        q = q.lte("price", max_price)

    if in_stock:
        q = q.gt("stock", 0)

    offset = (page - 1) * page_size
    result = q.range(offset, offset + page_size - 1).execute()
    total: int = result.count or 0

    return {
        "items": result.data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": -(-total // page_size),
    }


@router.get("/products/{slug}")
def get_product(slug: str) -> dict[str, Any]:
    sb = get_admin_supabase()
    result = (
        sb.table("products")
        .select("*, categories(name, slug), product_images(*)")
        .eq("slug", slug)
        .eq("is_active", True)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return result.data


@router.post(
    "/products",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_product(payload: ProductCreate) -> dict[str, Any]:
    sb = get_admin_supabase()
    data = payload.model_dump()
    data["price"] = float(data["price"])
    if data.get("compare_price"):
        data["compare_price"] = float(data["compare_price"])
    result = sb.table("products").insert(data).execute()
    return result.data[0]


@router.patch(
    "/products/{product_id}",
    dependencies=[Depends(require_admin)],
)
def update_product(product_id: str, payload: ProductUpdate) -> dict[str, Any]:
    sb = get_admin_supabase()
    data: dict[str, Any] = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
    }
    if "price" in data and data["price"]:
        data["price"] = float(data["price"])
    if "compare_price" in data and data["compare_price"]:
        data["compare_price"] = float(data["compare_price"])

    result = sb.table("products").update(data).eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return result.data[0]


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_product(product_id: str) -> None:
    sb = get_admin_supabase()
    sb.table("products").update({"is_active": False}).eq("id", product_id).execute()


# ── Image Upload ──────────────────────────────────────────────────────────────

@router.post(
    "/products/{product_id}/image",
    dependencies=[Depends(require_admin)],
)
async def upload_product_image(
    product_id: str,
    file: UploadFile = File(...),
) -> dict[str, str]:
    contents: bytes = await file.read()

    # 1. Raw size check (5MB max)
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum 5MB allowed.",
        )

    # 2. Magic bytes check — content-type header trusted nahi (spoof possible)
    if not _is_real_image(contents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Only JPEG, PNG, GIF, or WebP allowed.",
        )

    # 3. Product existence check
    sb = get_admin_supabase()
    product = (
        sb.table("products")
        .select("id")   # slug nahi — slug change hone pe image orphan hoti thi
        .eq("id", product_id)
        .single()
        .execute()
    )
    if not product.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # 4. PIL open + dimension check (decompression bomb protection)
    # Image.MAX_IMAGE_PIXELS already set globally at top of file
    try:
        img = Image.open(io.BytesIO(contents))
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image dimensions too large. Maximum ~10 megapixels allowed.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("PIL failed to open image: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not process image file.",
        )

    # 5. Optimize — RGB convert + resize + WebP compress
    img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=80)
    optimized: bytes = buffer.getvalue()

    # 6. Upload — path uses product_id (not slug) so rename-safe
    path = f"products/{product_id}.webp"
    sb.storage.from_("product-images").upload(
        path,
        optimized,
        {"content-type": "image/webp", "upsert": "true"},
    )

    url: str = sb.storage.from_("product-images").get_public_url(path)
    sb.table("products").update({"image_url": url}).eq("id", product_id).execute()

    logger.info("Image uploaded for product %s → %s", product_id, path)
    return {"image_url": url}