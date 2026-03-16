import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/orders", tags=["Orders"])

SHIPPING_THRESHOLD = Decimal("75.00")
SHIPPING_FLAT      = Decimal("9.99")
TAX_RATE           = Decimal("0.08")
MAX_ITEMS_PER_ORDER = 50

VALID_STATUSES: set[str] = {"pending", "paid", "shipped", "delivered", "cancelled"}

# Valid status transitions — invalid moves block karo
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending":   {"paid", "cancelled"},
    "paid":      {"shipped", "cancelled"},
    "shipped":   {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


def _sanitize_notes(notes: str | None) -> str | None:
    """Basic HTML strip — stored XSS prevent karo."""
    if notes is None:
        return None
    import re
    return re.sub(r"<[^>]+>", "", notes).strip()


# ── Request models ─────────────────────────────────────────────────────────────

class OrderItemInput(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=100)


class OrderCreate(BaseModel):
    items: list[OrderItemInput] = Field(min_length=1, max_length=MAX_ITEMS_PER_ORDER)
    shipping_address_id: str
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("items")
    @classmethod
    def no_duplicate_products(cls, v: list[OrderItemInput]) -> list[OrderItemInput]:
        """Ek hi product_id do baar bheja toh double stock deduction hoga."""
        ids = [item.product_id for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate product_id in items is not allowed. Combine quantities instead.")
        return v


class OrderAdminUpdate(BaseModel):
    status: str | None = Field(default=None)
    tracking_number: str | None = Field(default=None, max_length=100)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v and v not in VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {VALID_STATUSES}")
        return v


# ── Create order ──────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_order(
    request: Request,
    payload: OrderCreate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    user_id: str = current["profile"]["id"]

    # Shipping address ownership verify
    addr_res = (
        sb.table("addresses")
        .select("*")
        .eq("id", payload.shipping_address_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not addr_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipping address not found",
        )
    addr = addr_res.data

    order_items: list[dict[str, Any]] = []
    subtotal = Decimal("0")

    # ── Phase 1: Sab products validate karo — koi DB write nahi ──────────────
    validated: list[tuple[OrderItemInput, dict[str, Any]]] = []
    for item_in in payload.items:
        prod_res = (
            sb.table("products")
            .select("*")
            .eq("id", item_in.product_id)
            .eq("is_active", True)
            .single()
            .execute()
        )
        if not prod_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {item_in.product_id} not found or inactive",
            )
        prod = prod_res.data

        if prod["stock"] < item_in.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock for '{prod['name']}' (available: {prod['stock']})",
            )
        validated.append((item_in, prod))

    # ── Phase 2: Sab valid — atomic stock deduct karo ────────────────────────
    deducted: list[tuple[str, int]] = []
    try:
        for item_in, prod in validated:
            # .gte("stock", quantity) = atomic guard — race condition protection
            update_res = (
                sb.table("products")
                .update({"stock": prod["stock"] - item_in.quantity})
                .eq("id", prod["id"])
                .gte("stock", item_in.quantity)
                .execute()
            )
            if not update_res.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Insufficient stock for '{prod['name']}' — try again",
                )

            deducted.append((prod["id"], item_in.quantity))

            line = Decimal(str(prod["price"])) * item_in.quantity
            subtotal += line
            order_items.append({
                "product_id": prod["id"],
                "product_name": prod["name"],
                "unit_price": float(prod["price"]),
                "quantity": item_in.quantity,
                "subtotal": float(line),
            })

    except HTTPException:
        # Rollback — jo stock cut hua, atomic increment se wapas karo
        for product_id, qty in deducted:
            try:
                sb.rpc("increment_stock", {"p_id": product_id, "p_qty": qty}).execute()
            except Exception as e:
                logger.error(
                    "CRITICAL: Failed to rollback stock for product %s qty %d: %s",
                    product_id, qty, e,
                )
        raise

    # ── Pricing ───────────────────────────────────────────────────────────────
    shipping = Decimal("0") if subtotal >= SHIPPING_THRESHOLD else SHIPPING_FLAT
    tax = (subtotal + shipping) * TAX_RATE
    total = subtotal + shipping + tax

    order_data: dict[str, Any] = {
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
        "notes": _sanitize_notes(payload.notes),
    }

    # ── DB insert ─────────────────────────────────────────────────────────────
    # Ideally: Supabase RPC mein ek transaction mein karo
    # TODO: create_order_txn(order_data, items) RPC function banana hai
    order_res = sb.table("orders").insert(order_data).execute()
    order = order_res.data[0]

    for item in order_items:
        item["order_id"] = order["id"]

    try:
        sb.table("order_items").insert(order_items).execute()
    except Exception as e:
        logger.error("CRITICAL: order_items insert failed for order %s: %s", order["id"], e)
        # Stock rollback for orphan order
        for product_id, qty in deducted:
            try:
                sb.rpc("increment_stock", {"p_id": product_id, "p_qty": qty}).execute()
            except Exception as re:
                logger.error("Stock rollback failed: product=%s qty=%d err=%s", product_id, qty, re)
        sb.table("orders").delete().eq("id", order["id"]).execute()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order creation failed. Please try again.",
        )

    return (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("id", order["id"])
        .single()
        .execute()
        .data
    )


# ── My orders ─────────────────────────────────────────────────────────────────

@router.get("/my")
def my_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    sb = get_admin_supabase()
    result = (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("customer_id", current["profile"]["id"])
        .order("created_at", desc=True)
        .range(skip, skip + limit - 1)
        .execute()
    )
    return result.data


@router.get("/my/{order_id}")
def get_my_order(
    order_id: str,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    result = (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("id", order_id)
        .eq("customer_id", current["profile"]["id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return result.data


@router.post("/my/{order_id}/cancel")
def cancel_order(
    order_id: str,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    order_res = (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("id", order_id)
        .eq("customer_id", current["profile"]["id"])
        .single()
        .execute()
    )
    if not order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    order = order_res.data

    if order["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel order with status '{order['status']}'",
        )

    # Atomic stock restore — stale read se bachao
    for item in order.get("order_items", []):
        if item.get("product_id"):
            try:
                sb.rpc("increment_stock", {
                    "p_id": item["product_id"],
                    "p_qty": item["quantity"],
                }).execute()
            except Exception as e:
                logger.error(
                    "Stock restore failed on cancel: order=%s product=%s err=%s",
                    order_id, item["product_id"], e,
                )

    sb.table("orders").update({"status": "cancelled"}).eq("id", order_id).execute()
    return (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("id", order_id)
        .single()
        .execute()
        .data
    )


# ── Admin list ────────────────────────────────────────────────────────────────

@router.get("/", dependencies=[Depends(require_admin)])
def list_all_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = None,
) -> dict[str, Any]:
    sb = get_admin_supabase()
    q = (
        sb.table("orders")
        .select("*, order_items(*), users(email, full_name)", count="exact")
        .order("created_at", desc=True)
    )
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter. Valid: {VALID_STATUSES}",
            )
        q = q.eq("status", status_filter)

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


# ── Admin update ──────────────────────────────────────────────────────────────

@router.patch("/{order_id}", dependencies=[Depends(require_admin)])
def admin_update_order(order_id: str, payload: OrderAdminUpdate) -> dict[str, Any]:
    sb = get_admin_supabase()

    # Current order fetch karo — state machine check ke liye
    current_order_res = (
        sb.table("orders")
        .select("status")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not current_order_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    current_status: str = current_order_res.data["status"]

    # State machine validation — invalid transitions block karo
    if payload.status:
        allowed: set[str] = STATUS_TRANSITIONS.get(current_status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot transition from '{current_status}' to '{payload.status}'. "
                       f"Allowed: {allowed or 'none (terminal state)'}",
            )

    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    result = sb.table("orders").update(data).eq("id", order_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return result.data[0]