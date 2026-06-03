"""
Orders Router — Production Grade
================================
- POST /orders/ — Idempotent (idempotency_key accepted, NEVER returned)
- GET /orders/my — Sanitized response (no internal fields)
- GET /orders/my/{id} — Sanitized response (no internal fields)
- Pricing: DB pricing_config table (same as cart) ✅
- FIX: Prevented infinite stock inflation on cancel order race condition.
- FIX: Prevented permanent stock deduction on system network failures.
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
from app.services.pricing import get_pricing_from_config, StandardPricing, PriceBreakdown
from app.services.events import get_event_bus, OrderCreatedEvent, OrderShippedEvent, OrderStatusChangedEvent

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/orders", tags=["Orders"])

MAX_ITEMS_PER_ORDER = 50
ORDER_ITEMS_SELECT = "*, order_items(*, products(image_url, slug))"

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
STATUS_TRANSITIONS = {
    "pending":   {"paid", "cancelled"},
    "paid":      {"shipped", "cancelled", "refunded"},
    "shipped":   {"delivered"},
    "delivered": {"refunded"},
    "refunded":  set(),
    "cancelled": set(),
}

# 🔥 INTERNAL FIELDS — Kabhi API response mein expose mat karo
_INTERNAL_FIELDS = {
    "idempotency_key",
    "stripe_payment_intent",
    "customer_id",
    "updated_at",
}

# 🔥 SENSITIVE FIELDS — Mask karke bhejo
_MASKED_FIELDS = {
    "stripe_payment_intent": lambda v: f"pi_***{v[-4:]}" if v and len(v) > 4 else None,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_pricing_config(sb: Any) -> dict[str, Any]:
    """
    Fetch pricing config from DB — SAME as cart.
    SINGLE SOURCE OF TRUTH: pricing_config table.
    """
    try:
        res = (
            sb.table("pricing_config")
            .select("*").limit(1).single().execute()
        )
        if res and res.data:
            return res.data
    except Exception as e:
        logger.warning("pricing_config fetch failed, using fallback: %s", e)

    # Fallback — matches DB defaults
    return {
        "tax_rate": 18.0,
        "shipping_flat": 99.0,
        "shipping_threshold": 999.0,
        "currency": "INR",
        "tax_enabled": True,
        "shipping_enabled": True,
    }


def _calculate_pricing(sb: Any, subtotal: Decimal) -> PriceBreakdown:
    """
    Calculate pricing using DB config — SAME as cart.
    Ensures cart and orders always produce identical pricing.
    """
    config = _fetch_pricing_config(sb)
    pricing = get_pricing_from_config(config)
    return pricing.calculate(subtotal)


def _sanitize_notes(notes: str | None) -> str | None:
    if notes is None: return None
    return re.sub(r"<[^>]+>", "", notes).strip()


def _sanitize_order(order: dict) -> dict:
    """Amazon/Flipkart style — strip internal fields before response"""
    if not order: return order

    sanitized = {k: v for k, v in order.items() if k not in _INTERNAL_FIELDS}

    for field, mask_fn in _MASKED_FIELDS.items():
        if field in sanitized:
            sanitized[field] = mask_fn(sanitized[field])

    if "order_items" in sanitized:
        sanitized["order_items"] = [
            {k: v for k, v in item.items() if k not in {"order_id", "created_at", "updated_at"}}
            for item in sanitized["order_items"]
        ]

    for item in sanitized.get("order_items", []):
        if "products" in item and isinstance(item["products"], dict):
            item["product_slug"] = item["products"].get("slug")
            item["product_image_url"] = item["products"].get("image_url")
            del item["products"]

    return sanitized


def _sanitize_order_list(orders: list) -> list:
    return [_sanitize_order(o) for o in orders]


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrderItemInput(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100)


class OrderCreate(BaseModel):
    items: list[OrderItemInput] = Field(min_length=1, max_length=MAX_ITEMS_PER_ORDER)
    shipping_address_id: UUID
    notes: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=64)

    @field_validator("items")
    @classmethod
    def no_duplicate_products(cls, v):
        ids = [str(item.product_id) for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate product_id not allowed — combine quantities instead.")
        return v

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, v):
        if v is not None and not re.match(r'^[a-zA-Z0-9\-_]{8,64}$', v):
            raise ValueError("Invalid idempotency_key format")
        return v


class OrderAdminUpdate(BaseModel):
    status: str | None = Field(default=None)
    tracking_number: str | None = Field(default=None, max_length=100)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v and v not in VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {VALID_STATUSES}")
        return v


# ══════════════════════════════════════════════════════════════════════════════
#  POST /orders/ — Create Order (Idempotent + DB Pricing)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_order(
    request: Request,
    payload: OrderCreate,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create order. Idempotent + DB pricing (same as cart)."""
    sb = get_admin_supabase()
    user_id = current["profile"]["id"]

    # ── IDEMPOTENCY CHECK ─────────────────────────────────────────────────
    if payload.idempotency_key:
        try:
            existing = (
                sb.table("orders")
                .select(ORDER_ITEMS_SELECT)
                .eq("customer_id", user_id)
                .eq("idempotency_key", payload.idempotency_key)
                .maybe_single()
                .execute()
            )
            if existing and existing.data:
                logger.info("Idempotent return | user=%.8s", user_id)
                return _sanitize_order(existing.data)
        except Exception as e:
            logger.warning("Idempotency check failed (proceeding): %s", e)

    # ── Address ───────────────────────────────────────────────────────────
    addr_res = (
        sb.table("addresses").select("*")
        .eq("id", str(payload.shipping_address_id)).eq("user_id", user_id)
        .maybe_single().execute()
    )
    if not addr_res or not addr_res.data:
        raise HTTPException(404, "Shipping address not found")
    addr = addr_res.data

    # ── Products ──────────────────────────────────────────────────────────
    product_ids = [str(item.product_id) for item in payload.items]
    prods_res = (
        sb.table("products").select("*")
        .in_("id", product_ids).eq("is_active", True).execute()
    )
    if not prods_res or not prods_res.data:
        raise HTTPException(404, "Products not found")
    prod_map = {p["id"]: p for p in prods_res.data}

    # ── Validate stock ────────────────────────────────────────────────────
    for item in payload.items:
        p = prod_map.get(str(item.product_id))
        if not p:
            raise HTTPException(404, f"Product {item.product_id} not found")
        if p["stock"] < item.quantity:
            raise HTTPException(409, f"Insufficient stock: {p['name']}")

    # ── Stock deduct + line items ─────────────────────────────────────────
    order_items, subtotal, deducted = [], Decimal("0"), []
    try:
        for item in payload.items:
            p = prod_map[str(item.product_id)]
            if not decrement_stock(sb, p["id"], item.quantity, p["name"]):
                raise HTTPException(409, f"Stock conflict: {p['name']}")
            deducted.append((p["id"], item.quantity))
            lt = Decimal(str(p["price"])) * item.quantity
            subtotal += lt
            order_items.append({
                "product_id": p["id"], "product_name": p["name"],
                "unit_price": float(p["price"]), "quantity": item.quantity,
                "subtotal": float(lt),
            })
    except HTTPException:
        for pid, qty in deducted: restore_stock(sb, pid, qty, "rollback")
        raise

    # ── 🔥 PRICING FROM DB (SAME AS CART) ────────────────────────────────
    breakdown = _calculate_pricing(sb, subtotal)

    # ── Insert Order ──────────────────────────────────────────────────────
    order_data = {
        "customer_id": user_id,
        "shipping_address_id": str(payload.shipping_address_id),
        **breakdown.as_dict(),
        "shipping_line1": addr["line1"], "shipping_line2": addr.get("line2"),
        "shipping_city": addr["city"], "shipping_state": addr.get("state"),
        "shipping_postal_code": addr["postal_code"], "shipping_country": addr["country"],
        "notes": _sanitize_notes(payload.notes),
        "idempotency_key": payload.idempotency_key,
    }

    try:
        order_res = sb.table("orders").insert(order_data).execute()
    except PostgrestError as e:
        if payload.idempotency_key and "unique" in str(e).lower():
            for pid, qty in deducted: restore_stock(sb, pid, qty, "race")
            existing = (
                sb.table("orders").select(ORDER_ITEMS_SELECT)
                .eq("customer_id", user_id).eq("idempotency_key", payload.idempotency_key)
                .maybe_single().execute()
            )
            if existing and existing.data:
                return _sanitize_order(existing.data)
        for pid, qty in deducted: restore_stock(sb, pid, qty, "fail_db")
        raise HTTPException(500, "Order creation failed (Database Error)")
    except Exception as e:
        # Prevent stock leak if network fails during DB insert
        logger.error("System error during order creation: %s", e)
        for pid, qty in deducted: restore_stock(sb, pid, qty, "fail_sys")
        raise HTTPException(500, "Order creation failed (System Error)")

    order = order_res.data[0]
    for item in order_items: item["order_id"] = order["id"]

    try:
        sb.table("order_items").insert(order_items).execute()
    except Exception:
        for pid, qty in deducted: restore_stock(sb, pid, qty, "items_fail")
        sb.table("orders").update({"status": "cancelled"}).eq("id", order["id"]).execute()
        raise HTTPException(500, "Order items creation failed")

    full = (
        sb.table("orders").select(ORDER_ITEMS_SELECT)
        .eq("id", order["id"]).maybe_single().execute()
    )
    result = _sanitize_order(full.data if full and full.data else order)

    try:
        get_event_bus().publish(OrderCreatedEvent(
            order=result, customer_email=current["profile"]["email"], customer_id=user_id
        ))
    except Exception as e:
        logger.warning("Event failed: %s", e)

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  GET /orders/my — List Orders (Sanitized)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/my")
def my_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None),
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    offset = (page - 1) * page_size

    q = (
        sb.table("orders")
        .select(ORDER_ITEMS_SELECT, count="exact")
        .eq("customer_id", current["profile"]["id"])
        .order("created_at", desc=True)
    )
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(400, f"Invalid status: {status_filter}")
        q = q.eq("status", status_filter)

    result = q.range(offset, offset + page_size - 1).execute()
    total = result.count or 0

    return {
        "items": _sanitize_order_list(result.data or []),
        "total": total, "page": page, "page_size": page_size,
        "pages": -(-total // page_size) if page_size > 0 else 0,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  GET /orders/my/{order_id}
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/my/{order_id}")
def get_my_order(
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    result = (
        sb.table("orders").select(ORDER_ITEMS_SELECT)
        .eq("id", str(order_id)).eq("customer_id", current["profile"]["id"])
        .maybe_single().execute()
    )
    if not result or not result.data:
        raise HTTPException(404, "Order not found")
    return _sanitize_order(result.data)


# ══════════════════════════════════════════════════════════════════════════════
#  POST /orders/my/{order_id}/cancel
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/my/{order_id}/cancel")
def cancel_order(
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    order_res = (
        sb.table("orders").select(ORDER_ITEMS_SELECT)
        .eq("id", str(order_id)).eq("customer_id", current["profile"]["id"])
        .maybe_single().execute()
    )
    if not order_res or not order_res.data:
        raise HTTPException(404, "Order not found")

    order = order_res.data
    if order["status"] != "pending":
        raise HTTPException(409, f"Cannot cancel '{order['status']}' order")

    # DB me pehle status update hoga. Race conditions block hogi.
    update_res = (
        sb.table("orders")
        .update({"status": "cancelled"})
        .eq("id", str(order_id))
        .eq("status", "pending")
        .execute()
    )

    if not update_res or not hasattr(update_res, "data") or not update_res.data:
        raise HTTPException(409, "Order status could not be changed or is already updated")

    # Ab perfectly safe hai stock restore karna.
    for item in order.get("order_items", []):
        if item.get("product_id"):
            restore_stock(sb, item["product_id"], item["quantity"], f"cancel:{order_id}")

    return {"status": "cancelled", "order_id": str(order_id)}


# ══════════════════════════════════════════════════════════════════════════════
#  GET /orders/ — Admin List
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/", dependencies=[Depends(require_admin)])
def list_all_orders(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
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
            raise HTTPException(400, f"Invalid status: {status_filter}")
        q = q.eq("status", status_filter)

    offset = (page - 1) * page_size
    result = q.range(offset, offset + page_size - 1).execute()
    total = result.count or 0

    return {
        "items": _sanitize_order_list(result.data or []),
        "total": total, "page": page, "page_size": page_size,
        "pages": -(-total // page_size) if page_size > 0 else 0,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  PATCH /orders/{order_id} — Admin Update
# ══════════════════════════════════════════════════════════════════════════════

@router.patch("/{order_id}", dependencies=[Depends(require_admin)])
def admin_update_order(order_id: UUID, payload: OrderAdminUpdate) -> dict[str, Any]:
    sb = get_admin_supabase()
    current_res = (
        sb.table("orders").select("status, stripe_payment_intent, customer_id")
        .eq("id", str(order_id)).maybe_single().execute()
    )
    if not current_res or not current_res.data:
        raise HTTPException(404, "Order not found")

    current_status = current_res.data["status"]

    if payload.status:
        allowed = STATUS_TRANSITIONS.get(current_status, set())
        if payload.status not in allowed:
            raise HTTPException(409, f"Cannot move '{current_status}' → '{payload.status}'")
        if payload.status == "refunded":
            pi_id = current_res.data.get("stripe_payment_intent")
            if pi_id:
                try:
                    import stripe
                    stripe.api_key = settings.STRIPE_SECRET_KEY
                    stripe.Refund.create(payment_intent=pi_id)
                except Exception as e:
                    raise HTTPException(502, f"Refund failed: {e}")

    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    result = (
        sb.table("orders").update(data)
        .eq("id", str(order_id)).eq("status", current_status).execute()
    )
    if not result or not result.data:
        raise HTTPException(409, "Order modified — refresh and retry")

    if payload.status == "shipped":
        try:
            order = result.data[0]
            customer_id = current_res.data["customer_id"]
            user_res = sb.table("users").select("email").eq("id", customer_id).maybe_single().execute()
            if user_res and user_res.data:
                get_event_bus().publish(OrderShippedEvent(
                    order=order, customer_email=user_res.data["email"],
                    customer_id=customer_id, tracking_number=payload.tracking_number,
                ))
        except Exception as e:
            logger.warning("Shipped event: %s", e)

    if payload.status in ("delivered", "refunded"):
        try:
            get_event_bus().publish(OrderStatusChangedEvent(
                order=result.data[0], customer_id=current_res.data["customer_id"],
                old_status=current_status, new_status=payload.status,
            ))
        except Exception as e:
            logger.warning("Status event: %s", e)

    return _sanitize_order(result.data[0])
