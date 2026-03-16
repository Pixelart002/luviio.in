    import logging
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from postgrest.exceptions import APIError as PostgrestError

from app.config import settings
from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase
from app.utils.stock import restore_stock, decrement_stock
from app.utils.email import send_order_confirmation, send_order_shipped

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/orders", tags=["Orders"])

MAX_ITEMS_PER_ORDER = 50

VALID_STATUSES: set[str] = {
    "pending", "paid", "shipped", "delivered", "cancelled", "refunded"
}

STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending":   {"paid", "cancelled"},
    "paid":      {"shipped", "cancelled", "refunded"},
    "shipped":   {"delivered"},
    "delivered": {"refunded"},
    "refunded":  set(),
    "cancelled": set(),
}


def _sanitize_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    return re.sub(r"<[^>]+>", "", notes).strip()


# ── Models ────────────────────────────────────────────────────────────────────

class OrderItemInput(BaseModel):
    product_id: UUID  # galat format pe FastAPI 422 dega, 500 nahi
    quantity: int = Field(ge=1, le=100)


class OrderCreate(BaseModel):
    items: list[OrderItemInput] = Field(min_length=1, max_length=MAX_ITEMS_PER_ORDER)
    shipping_address_id: UUID  # UUID type — galat format pe FastAPI 422 dega, 500 nahi
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("items")
    @classmethod
    def no_duplicate_products(cls, v: list[OrderItemInput]) -> list[OrderItemInput]:
        ids = [item.product_id for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate product_id not allowed — combine quantities instead.")
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

    try:
        addr_res = (
            sb.table("addresses")
            .select("*")
            .eq("id", str(payload.shipping_address_id))
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except PostgrestError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid shipping_address_id format",
        )
    if not addr_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipping address not found")
    addr = addr_res.data

    # ── Phase 1: Batch fetch + validate — no DB writes ────────────────────────
    product_ids = [str(item.product_id) for item in payload.items]
    try:
        prods_res = (
            sb.table("products")
            .select("*")
            .in_("id", product_ids)
            .eq("is_active", True)
            .execute()
        )
    except PostgrestError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product_id format",
        )
    prod_map: dict[str, dict[str, Any]] = {p["id"]: p for p in prods_res.data}

    validated: list[tuple[OrderItemInput, dict[str, Any]]] = []
    for item_in in payload.items:
        prod = prod_map.get(item_in.product_id)
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {item_in.product_id} not found or inactive",
            )
        if prod["stock"] < item_in.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Insufficient stock for '{prod['name']}' (available: {prod['stock']})",
            )
        validated.append((item_in, prod))

    # ── Phase 2: Atomic stock deduct via RPC ──────────────────────────────────
    order_items: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    deducted: list[tuple[str, int]] = []

    try:
        for item_in, prod in validated:
            ok = decrement_stock(sb, prod["id"], item_in.quantity, prod["name"])
            if not ok:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Insufficient stock for '{prod['name']}' — please try again",
                )
            deducted.append((prod["id"], item_in.quantity))

            line = Decimal(str(prod["price"])) * item_in.quantity
            subtotal += line
            order_items.append({
                "product_id":   prod["id"],
                "product_name": prod["name"],
                "unit_price":   float(prod["price"]),
                "quantity":     item_in.quantity,
                "subtotal":     float(line),
            })
    except HTTPException:
        for pid, qty in deducted:
            restore_stock(sb, pid, qty, "create_order_rollback")
        raise

    # ── Pricing (from config — change without redeploy) ───────────────────────
    shipping = Decimal("0") if subtotal >= settings.SHIPPING_THRESHOLD else settings.SHIPPING_FLAT
    tax      = (subtotal + shipping) * settings.TAX_RATE
    total    = subtotal + shipping + tax

    order_data: dict[str, Any] = {
        "customer_id":           user_id,
        "shipping_address_id":   str(payload.shipping_address_id),  # traceability
        "subtotal":              float(subtotal),
        "shipping_cost":         float(shipping),
        "tax_amount":            float(tax.quantize(Decimal("0.01"))),
        "total_amount":          float(total.quantize(Decimal("0.01"))),
        "shipping_line1":        addr["line1"],
        "shipping_line2":        addr.get("line2"),
        "shipping_city":         addr["city"],
        "shipping_state":        addr.get("state"),
        "shipping_postal_code":  addr["postal_code"],
        "shipping_country":      addr["country"],
        "notes":                 _sanitize_notes(payload.notes),
    }

    # ── DB insert ─────────────────────────────────────────────────────────────
    order_res = sb.table("orders").insert(order_data).execute()
    order = order_res.data[0]

    for item in order_items:
        item["order_id"] = order["id"]

    try:
        sb.table("order_items").insert(order_items).execute()
    except Exception as e:
        logger.error("CRITICAL: order_items insert failed for order %s: %s", order["id"], e)
        for pid, qty in deducted:
            restore_stock(sb, pid, qty, "order_items_insert_fail")
        try:
            sb.table("orders").delete().eq("id", order["id"]).execute()
        except Exception as del_err:
            logger.error("CRITICAL: Orphan order cleanup failed %s: %s", order["id"], del_err)
            sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order creation failed. Please try again.",
        )

    full_order = (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("id", order["id"])
        .single()
        .execute()
        .data
    )

    # Send confirmation email (non-blocking — failure won't break order)
    send_order_confirmation(current["profile"]["email"], full_order)

    return full_order


# ── My orders ─────────────────────────────────────────────────────────────────

@router.get("/my")
def my_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    offset = (page - 1) * page_size
    result = (
        sb.table("orders")
        .select("*, order_items(*)", count="exact")
        .eq("customer_id", current["profile"]["id"])
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    total: int = result.count or 0
    return {
        "items":     result.data,
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     -(-total // page_size),
    }


@router.get("/my/{order_id}")
def get_my_order(
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    result = (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("id", str(order_id))
        .eq("customer_id", current["profile"]["id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return result.data


@router.post("/my/{order_id}/cancel")
def cancel_order(
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    order_res = (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("id", str(order_id))
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

    for item in order.get("order_items", []):
        if item.get("product_id"):
            restore_stock(sb, item["product_id"], item["quantity"], f"cancel:{order_id}")

    sb.table("orders").update({"status": "cancelled"}).eq("id", str(order_id)).execute()
    return (
        sb.table("orders")
        .select("*, order_items(*)")
        .eq("id", str(order_id))
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
                detail=f"Invalid status. Valid: {VALID_STATUSES}",
            )
        q = q.eq("status", status_filter)

    offset = (page - 1) * page_size
    result = q.range(offset, offset + page_size - 1).execute()
    total: int = result.count or 0
    return {
        "items":     result.data,
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     -(-total // page_size),
    }


# ── Admin update ──────────────────────────────────────────────────────────────

@router.patch("/{order_id}", dependencies=[Depends(require_admin)])
def admin_update_order(order_id: UUID, payload: OrderAdminUpdate) -> dict[str, Any]:
    sb = get_admin_supabase()

    current_res = (
        sb.table("orders")
        .select("status, stripe_payment_intent, customer_id")
        .eq("id", str(order_id))
        .single()
        .execute()
    )
    if not current_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    current_status: str = current_res.data["status"]

    if payload.status:
        allowed: set[str] = STATUS_TRANSITIONS.get(current_status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot move '{current_status}' → '{payload.status}'. "
                    f"Allowed: {allowed or 'none (terminal state)'}"
                ),
            )

        # Auto-refund via Stripe when moving to refunded
        if payload.status == "refunded":
            pi_id = current_res.data.get("stripe_payment_intent")
            if pi_id:
                try:
                    import stripe
                    from app.config import settings as cfg
                    stripe.api_key = cfg.STRIPE_SECRET_KEY
                    stripe.Refund.create(payment_intent=pi_id)
                    logger.info("Stripe refund created for order %s", order_id)
                except Exception as e:
                    logger.error("Stripe refund failed for order %s: %s", order_id, e)
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Stripe refund failed: {e}",
                    )

    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}

    # TOCTOU fix — conditional update with current status guard
    result = (
        sb.table("orders")
        .update(data)
        .eq("id", str(order_id))
        .eq("status", current_status)  # atomic guard
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order status changed by another request. Please refresh and try again.",
        )

    # Send shipped email
    if payload.status == "shipped":
        try:
            order = result.data[0]
            user_res = sb.table("users").select("email").eq("id", order["customer_id"]).single().execute()
            if user_res.data:
                send_order_shipped(user_res.data["email"], order, payload.tracking_number)
        except Exception as e:
            logger.warning("Failed to send shipped email: %s", e)

    return result.data[0]