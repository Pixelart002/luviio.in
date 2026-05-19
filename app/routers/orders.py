"""
Orders Router
=============
Handles order creation, user order history, cancellations, and admin updates.
INCLUDES FIXES FOR:
  - Customer ID correctly passed to OrderCreatedEvent and OrderShippedEvent
  - Safe Supabase data resolution to prevent 'NoneType' crashes
  - Product image_url joined via products table for order item display
  - Idempotency support to prevent duplicate orders
"""
import logging
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from postgrest.exceptions import APIError as PostgrestError
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase
from app.utils.stock import restore_stock, decrement_stock
from app.services.pricing import get_default_pricing
from app.services.events import get_event_bus, OrderCreatedEvent, OrderShippedEvent

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/orders", tags=["Orders"])

MAX_ITEMS_PER_ORDER = 50

# ── Select string with product image join ─────────────────────────────────────
# products(image_url, slug) gives us the image without storing it in order_items
ORDER_ITEMS_SELECT = "*, order_items(*, products(image_url, slug))"

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
    """Removes HTML tags and strips whitespace from notes."""
    if notes is None:
        return None
    return re.sub(r"<[^>]+>", "", notes).strip()


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrderItemInput(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100)


class OrderCreate(BaseModel):
    items: list[OrderItemInput] = Field(min_length=1, max_length=MAX_ITEMS_PER_ORDER)
    shipping_address_id: UUID
    idempotency_key: UUID
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


# ── POST /orders/ ─────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_order(
    request: Request,
    payload: OrderCreate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    user_id: str = current["profile"]["id"]

    # Check for existing order (Idempotency)
    existing = sb.table("orders").select("*").match({
        "customer_id": user_id,
        "idempotency_key": str(payload.idempotency_key)
    }).maybe_single().execute()
    
    # FIX: Check if existing is not None and has data attribute
    if existing and hasattr(existing, "data") and existing.data:
        return existing.data

    try:
        addr_res = (
            sb.table("addresses")
            .select("*")
            .eq("id", str(payload.shipping_address_id))
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.error(f"Error fetching address {payload.shipping_address_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to verify address")

    if not addr_res or not hasattr(addr_res, "data") or not addr_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipping address not found")

    addr = addr_res.data
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid product request format")

    if not prods_res or not hasattr(prods_res, "data") or not prods_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more products could not be found.")

    prod_map: dict[str, dict[str, Any]] = {p["id"]: p for p in prods_res.data}

    validated: list[tuple[OrderItemInput, dict[str, Any]]] = []
    for item_in in payload.items:
        prod = prod_map.get(str(item_in.product_id))
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

    pricing   = get_default_pricing()
    breakdown = pricing.calculate(subtotal)

    order_data: dict[str, Any] = {
        "customer_id":           user_id,
        "idempotency_key":       str(payload.idempotency_key),
        "shipping_address_id":   str(payload.shipping_address_id),
        **breakdown.as_dict(),
        "shipping_line1":        addr["line1"],
        "shipping_line2":        addr.get("line2"),
        "shipping_city":         addr["city"],
        "shipping_state":        addr.get("state"),
        "shipping_postal_code":  addr["postal_code"],
        "shipping_country":      addr["country"],
        "notes":                 _sanitize_notes(payload.notes),
    }

    order_res = sb.table("orders").insert(order_data).execute()

    if not order_res or not hasattr(order_res, "data") or not order_res.data:
        for pid, qty in deducted:
            restore_stock(sb, pid, qty, "create_order_insert_fail")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create order record")

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

    full_order_res = (
        sb.table("orders")
        .select(ORDER_ITEMS_SELECT)
        .eq("id", order["id"])
        .maybe_single()
        .execute()
    )
    full_order = full_order_res.data if full_order_res and hasattr(full_order_res, "data") else order

    logger.info("Publishing OrderCreatedEvent | order=%s customer=%s", order["id"][:8], user_id[:8])
    try:
        get_event_bus().publish(OrderCreatedEvent(
            order=full_order,
            customer_email=current["profile"]["email"],
            customer_id=user_id,
        ))
    except Exception as e:
        logger.warning(f"Event bus failed to publish OrderCreatedEvent: {e}")

    return full_order


# ── GET /orders/my ────────────────────────────────────────────────────────────

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
        .select(ORDER_ITEMS_SELECT, count="exact")
        .eq("customer_id", current["profile"]["id"])
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    total: int = result.count or 0
    return {
        "items":     result.data if result and hasattr(result, "data") else [],
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     -(-total // page_size) if page_size > 0 else 0,
    }


# ── GET /orders/my/{order_id} ─────────────────────────────────────────────────

@router.get("/my/{order_id}")
def get_my_order(
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    result = (
        sb.table("orders")
        .select(ORDER_ITEMS_SELECT)
        .eq("id", str(order_id))
        .eq("customer_id", current["profile"]["id"])
        .maybe_single()
        .execute()
    )
    if not result or not hasattr(result, "data") or not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return result.data


# ── POST /orders/my/{order_id}/cancel ─────────────────────────────────────────

@router.post("/my/{order_id}/cancel")
def cancel_order(
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    order_res = (
        sb.table("orders")
        .select(ORDER_ITEMS_SELECT)
        .eq("id", str(order_id))
        .eq("customer_id", current["profile"]["id"])
        .maybe_single()
        .execute()
    )

    if not order_res or not hasattr(order_res, "data") or not order_res.data:
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

    updated_res = (
        sb.table("orders")
        .select(ORDER_ITEMS_SELECT)
        .eq("id", str(order_id))
        .maybe_single()
        .execute()
    )
    return updated_res.data if updated_res and hasattr(updated_res, "data") else {}


# ── GET /orders/ (Admin) ──────────────────────────────────────────────────────

@router.get("/", dependencies=[Depends(require_admin)])
def list_all_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = None,
) -> dict[str, Any]:
    sb = get_admin_supabase()
    q = (
        sb.table("orders")
        .select(f"{ORDER_ITEMS_SELECT}, users(email, full_name)", count="exact")
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
        "items":     result.data if result and hasattr(result, "data") else [],
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     -(-total // page_size) if page_size > 0 else 0,
    }


# ── PATCH /orders/{order_id} (Admin) ──────────────────────────────────────────

@router.patch("/{order_id}", dependencies=[Depends(require_admin)])
def admin_update_order(order_id: UUID, payload: OrderAdminUpdate) -> dict[str, Any]:
    sb = get_admin_supabase()

    current_res = (
        sb.table("orders")
        .select("status, stripe_payment_intent, customer_id")
        .eq("id", str(order_id))
        .maybe_single()
        .execute()
    )

    if not current_res or not hasattr(current_res, "data") or not current_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    current_status: str = current_res.data["status"]

    if payload.status:
        allowed: set[str] = STATUS_TRANSITIONS.get(current_status, set())
        if payload.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot move '{current_status}' to '{payload.status}'. "
                    f"Allowed transitions: {allowed or 'none (terminal state)'}"
                ),
            )

        if payload.status == "refunded":
            pi_id = current_res.data.get("stripe_payment_intent")
            if pi_id:
                try:
                    import stripe
                    stripe.api_key = settings.STRIPE_SECRET_KEY
                    stripe.Refund.create(payment_intent=pi_id)
                    logger.info("Stripe refund created for order %s", order_id)
                except Exception as e:
                    logger.error("Stripe refund failed for order %s: %s", order_id, e)
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Stripe refund failed: {e}",
                    )

    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}

    result = (
        sb.table("orders")
        .update(data)
        .eq("id", str(order_id))
        .eq("status", current_status)
        .execute()
    )

    if not result or not hasattr(result, "data") or not result.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order status changed by another request. Please refresh and try again.",
        )

    if payload.status == "shipped":
        try:
            order = result.data[0]
            customer_id = current_res.data["customer_id"]
            user_res = (
                sb.table("users")
                .select("email")
                .eq("id", customer_id)
                .maybe_single()
                .execute()
            )
            if user_res and hasattr(user_res, "data") and user_res.data:
                get_event_bus().publish(OrderShippedEvent(
                    order=order,
                    customer_email=user_res.data["email"],
                    customer_id=customer_id,
                    tracking_number=payload.tracking_number,
                ))
        except Exception as e:
            logger.warning("Failed to publish shipped event: %s", e)

    return result.data[0]
