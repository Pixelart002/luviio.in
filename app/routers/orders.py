from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from decimal import Decimal
from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase

router = APIRouter(prefix="/orders", tags=["Orders"])

SHIPPING_THRESHOLD = Decimal("75.00")
SHIPPING_FLAT      = Decimal("9.99")
TAX_RATE           = Decimal("0.08")
VALID_STATUSES     = {"pending", "paid", "shipped", "delivered", "cancelled"}


class OrderItemInput(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=100)

class OrderCreate(BaseModel):
    items: List[OrderItemInput] = Field(min_length=1)
    shipping_address_id: str
    notes: Optional[str] = Field(default=None, max_length=500)

class OrderAdminUpdate(BaseModel):
    status: Optional[str] = Field(default=None)
    tracking_number: Optional[str] = Field(default=None, max_length=100)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v and v not in VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {VALID_STATUSES}")
        return v


@router.post("/", status_code=201)
def create_order(payload: OrderCreate, current: dict = Depends(get_current_user)):
    sb = get_admin_supabase()
    user_id = current["profile"]["id"]

    addr_res = sb.table("addresses").select("*").eq("id", payload.shipping_address_id).eq("user_id", user_id).single().execute()
    if not addr_res.data:
        raise HTTPException(status_code=404, detail="Shipping address not found")
    addr = addr_res.data

    order_items = []
    subtotal = Decimal("0")

    for item_in in payload.items:
        prod_res = sb.table("products").select("*").eq("id", item_in.product_id).eq("is_active", True).single().execute()
        if not prod_res.data:
            raise HTTPException(status_code=404, detail=f"Product {item_in.product_id} not found")
        prod = prod_res.data

        if prod["stock"] < item_in.quantity:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock for '{prod['name']}' (available: {prod['stock']})"
            )

        # Atomic stock deduction — race condition fix
        update_res = sb.table("products")\
            .update({"stock": prod["stock"] - item_in.quantity})\
            .eq("id", prod["id"])\
            .gte("stock", item_in.quantity)\
            .execute()

        if not update_res.data:
            raise HTTPException(status_code=409, detail=f"Insufficient stock for '{prod['name']}'")

        line = Decimal(str(prod["price"])) * item_in.quantity
        subtotal += line
        order_items.append({
            "product_id": prod["id"],
            "product_name": prod["name"],
            "unit_price": float(prod["price"]),
            "quantity": item_in.quantity,
            "subtotal": float(line),
        })

    shipping = Decimal("0") if subtotal >= SHIPPING_THRESHOLD else SHIPPING_FLAT
    tax = (subtotal + shipping) * TAX_RATE
    total = subtotal + shipping + tax

    order_data = {
        "customer_id": user_id,
        "subtotal": float(subtotal),
        "shipping_cost": float(shipping),
        "tax_amount": float(tax.quantize(Decimal("0.01"))),
        "total_amount": float(total.quantize(Decimal("0.01"))),
        "shipping_line1": addr["line1"],
        "shipping_line2": addr.get("line2"),
        "shipping_city": addr["city"],
        "shipping_state": addr.get("state"),
        "shipping_postal_code": addr["postal_code"],
        "shipping_country": addr["country"],
        "notes": payload.notes,
    }

    order_res = sb.table("orders").insert(order_data).execute()
    order = order_res.data[0]

    for item in order_items:
        item["order_id"] = order["id"]
    sb.table("order_items").insert(order_items).execute()

    return sb.table("orders").select("*, order_items(*)").eq("id", order["id"]).single().execute().data


@router.get("/my")
def my_orders(
    skip: int = 0,
    limit: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user)
):
    sb = get_admin_supabase()
    result = sb.table("orders").select("*, order_items(*)")\
        .eq("customer_id", current["profile"]["id"])\
        .order("created_at", desc=True)\
        .range(skip, skip + limit - 1).execute()
    return result.data


@router.get("/my/{order_id}")
def get_my_order(order_id: str, current: dict = Depends(get_current_user)):
    sb = get_admin_supabase()
    result = sb.table("orders").select("*, order_items(*)")\
        .eq("id", order_id).eq("customer_id", current["profile"]["id"]).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    return result.data


@router.post("/my/{order_id}/cancel")
def cancel_order(order_id: str, current: dict = Depends(get_current_user)):
    sb = get_admin_supabase()
    order_res = sb.table("orders").select("*, order_items(*)")\
        .eq("id", order_id).eq("customer_id", current["profile"]["id"]).single().execute()
    if not order_res.data:
        raise HTTPException(status_code=404, detail="Order not found")
    order = order_res.data

    if order["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Cannot cancel order with status '{order['status']}'")

    for item in order.get("order_items", []):
        if item.get("product_id"):
            prod = sb.table("products").select("stock").eq("id", item["product_id"]).single().execute()
            if prod.data:
                sb.table("products").update({"stock": prod.data["stock"] + item["quantity"]}).eq("id", item["product_id"]).execute()

    sb.table("orders").update({"status": "cancelled"}).eq("id", order_id).execute()
    return sb.table("orders").select("*, order_items(*)").eq("id", order_id).single().execute().data


@router.get("/", dependencies=[Depends(require_admin)])
def list_all_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = None,
):
    sb = get_admin_supabase()
    q = sb.table("orders").select("*, order_items(*), users(email, full_name)", count="exact")\
        .order("created_at", desc=True)
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        q = q.eq("status", status_filter)
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


@router.patch("/{order_id}", dependencies=[Depends(require_admin)])
def admin_update_order(order_id: str, payload: OrderAdminUpdate):
    sb = get_admin_supabase()
    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    result = sb.table("orders").update(data).eq("id", order_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Order not found")
    return result.data[0]