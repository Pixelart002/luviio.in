from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal
from app.dependencies import require_admin
from app.supabase_client import get_admin_supabase

router = APIRouter(tags=["Products"])


class CategoryCreate(BaseModel):
    name: str = Field(max_length=100)
    slug: str = Field(max_length=120, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    image_url: Optional[str] = None

class ProductCreate(BaseModel):
    name: str = Field(max_length=255)
    slug: str = Field(max_length=280, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    short_description: Optional[str] = None
    sku: Optional[str] = Field(default=None, max_length=100)
    category_id: Optional[str] = None
    price: Decimal = Field(gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    stock: int = Field(ge=0, default=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    weight_grams: Optional[int] = Field(default=None, ge=0)
    image_url: Optional[str] = None
    is_active: bool = True

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, gt=0)
    compare_price: Optional[Decimal] = None
    stock: Optional[int] = Field(default=None, ge=0)
    low_stock_threshold: Optional[int] = None
    image_url: Optional[str] = None
    category_id: Optional[str] = None
    is_active: Optional[bool] = None
    weight_grams: Optional[int] = None


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories")
def list_categories():
    sb = get_admin_supabase()
    result = sb.table("categories").select("*").eq("is_active", True).execute()
    return result.data


@router.post("/categories", status_code=201, dependencies=[Depends(require_admin)])
def create_category(payload: CategoryCreate):
    sb = get_admin_supabase()
    result = sb.table("categories").insert(payload.model_dump()).execute()
    return result.data[0]


@router.delete("/categories/{category_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_category(category_id: str):
    sb = get_admin_supabase()
    sb.table("categories").update({"is_active": False}).eq("id", category_id).execute()


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(default=None, max_length=120),  # ← fix
    search: Optional[str] = Query(default=None, max_length=100),    # ← fix
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
):
    sb = get_admin_supabase()
    q = sb.table("products").select("*, categories(name, slug)", count="exact").eq("is_active", True)

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
    total = result.count or 0

    return {
        "items": result.data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": -(-total // page_size),
    }


@router.get("/products/{slug}")
def get_product(slug: str):
    sb = get_admin_supabase()
    result = sb.table("products").select("*, categories(name, slug), product_images(*)") \
        .eq("slug", slug).eq("is_active", True).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    return result.data


@router.post("/products", status_code=201, dependencies=[Depends(require_admin)])
def create_product(payload: ProductCreate):
    sb = get_admin_supabase()
    data = payload.model_dump()
    data["price"] = float(data["price"])
    if data.get("compare_price"):
        data["compare_price"] = float(data["compare_price"])
    result = sb.table("products").insert(data).execute()
    return result.data[0]


@router.patch("/products/{product_id}", dependencies=[Depends(require_admin)])
def update_product(product_id: str, payload: ProductUpdate):
    sb = get_admin_supabase()
    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if "price" in data and data["price"]:
        data["price"] = float(data["price"])
    if "compare_price" in data and data["compare_price"]:
        data["compare_price"] = float(data["compare_price"])
    result = sb.table("products").update(data).eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")
    return result.data[0]


@router.delete("/products/{product_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_product(product_id: str):
    sb = get_admin_supabase()
    sb.table("products").update({"is_active": False}).eq("id", product_id).execute()