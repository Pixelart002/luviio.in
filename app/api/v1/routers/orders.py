"""
Orders Router — Enterprise Grade
================================
Path: app/api/v1/routers/orders.py

Architecture Upgrades:
  1. 100% of Supabase DB calls moved to OrderRepository!
  2. Stripe SDK removed! Delegated to PaymentRegistry.
  3. Pricing logic fully migrated to Central PricingEngine.
"""
import logging
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from postgrest.exceptions import APIError as PostgrestError
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user, require_admin
from app.core.supabase import get_admin_supabase
from app.api.schemas.order_dto import OrderCreate, OrderAdminUpdate, VALID_STATUSES, OrderListResponse
from app.repositories.order_repo import OrderRepository
from app.services.stock import restore_stock, decrement_stock
from app.services.pricing import get_pricing_from_config
from app.services.events import get_event_bus, OrderCreatedEvent, OrderShippedEvent, OrderStatusChangedEvent
from app.integrations.payments.registry import get_payment_provider

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/orders", tags=["Orders"])

STATUS_TRANSITIONS = {
    "pending":   {"paid", "cancelled"},
    "paid":      {"shipped", "cancelled", "refunded"},
    "shipped":   {"delivered"},
    "delivered": {"refunded"},
    "refunded":  set(),
    "cancelled": set(),
}

_INTERNAL_FIELDS = {"idempotency_key", "stripe_payment_intent", "customer_id", "updated_at"}
_MASKED_FIELDS = {"stripe_payment_intent": lambda v: f"pi_***{v[-4:]}" if v and len(v) > 4 else None}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitize_notes(notes: str | None) -> str | None:
    if notes is None: return None
    return re.sub(r"<[^>]+>", "", notes).strip()

def _sanitize_order(order: dict) -> dict:
    if not order: return order
    sanitized = {k: v for k, v in order.items() if k not in _INTERNAL_FIELDS}
    for field, mask_fn in _MASKED_FIELDS.items():
        if field in sanitized: sanitized[field] = mask_fn(sanitized[field])
    if "order_items" in sanitized:
        sanitized["order_items"] = [{k: v for k, v in item.items() if k not in {"order_id", "created_at", "updated_at"}} for item in sanitized["order_items"]]
    for item in sanitized.get("order_items", []):
        if "products" in item and isinstance(item["products"], dict):
            item["product_slug"] = item["products"].get("slug")
            item["product_image_url"] = item["products"].get("image_url")
            del item["products"]
    return sanitized

def _sanitize_order_list(orders: list) -> list:
    return [_sanitize_order(o) for o in orders]

# ══════════════════════════════════════════════════════════════════════════════
#  POST /orders/ — Create Order
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_order(request: Request, payload: OrderCreate, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    repo = OrderRepository()
    sb_admin = get_admin_supabase() # Needed strictly for stock service injection
    user_id = current["profile"]["id"]
    
    if hasattr(request.state, "actions"): request.state.actions.append("Order creation pipeline initiated")

    # 1. Idempotency Check
    if payload.idempotency_key:
        existing = repo.get_order_by_idempotency_key(user_id, payload.idempotency_key)
        if existing:
            if hasattr(request.state, "actions"): request.state.actions.append("Idempotency match found! Returning existing order.")
            return _sanitize_order(existing)

    # 2. Shipping Address Validation
    addr = repo.get_shipping_address(str(payload.shipping_address_id), user_id)
    if not addr: raise HTTPException(404, "Shipping address not found")
    if hasattr(request.state, "actions"): request.state.actions.append("Shipping address validated")

    # 3. Product & Stock Validation
    product_ids = [str(item.product_id) for item in payload.items]
    prods = repo.get_active_products(product_ids)
    if not prods: raise HTTPException(404, "Products not found")
    prod_map = {p["id"]: p for p in prods}

    for item in payload.items:
        p = prod_map.get(str(item.product_id))
        if not p: raise HTTPException(404, f"Product {item.product_id} not found")
        if p["stock"] < item.quantity: raise HTTPException(409, f"Insufficient stock: {p['name']}")

    # 4. Stock Deduction (Atomic)
    order_items, subtotal, deducted = [], Decimal("0"), []
    try:
        for item in payload.items:
            p = prod_map[str(item.product_id)]
            if not decrement_stock(sb_admin, p["id"], item.quantity, p["name"]):
                raise HTTPException(409, f"Stock conflict: {p['name']}")
            deducted.append((p["id"], item.quantity))
            lt = Decimal(str(p["price"])) * item.quantity
            subtotal += lt
            order_items.append({
                "product_id": p["id"], "product_name": p["name"],
                "unit_price": float(p["price"]), "quantity": item.quantity, "subtotal": float(lt),
            })
    except HTTPException:
        for pid, qty in deducted: restore_stock(sb_admin, pid, qty, "rollback")
        raise

    # 5. Pricing via Engine
    config = repo.get_pricing_config()
    breakdown = get_pricing_from_config(config).calculate(subtotal)

    order_data = {
        "customer_id": user_id, "shipping_address_id": str(payload.shipping_address_id),
        **breakdown.as_dict(),
        "shipping_line1": addr["line1"], "shipping_line2": addr.get("line2"),
        "shipping_city": addr["city"], "shipping_state": addr.get("state"),
        "shipping_postal_code": addr["postal_code"], "shipping_country": addr["country"],
        "notes": _sanitize_notes(payload.notes), "idempotency_key": payload.idempotency_key,
    }

    # 6. DB Insert with Idempotency fallback
    try:
        order = repo.create_order_with_items(order_data, order_items)
    except PostgrestError as e:
        if payload.idempotency_key and "unique" in str(e).lower():
            for pid, qty in deducted: restore_stock(sb_admin, pid, qty, "race")
            existing = repo.get_order_by_idempotency_key(user_id, payload.idempotency_key)
            if existing: return _sanitize_order(existing)
        for pid, qty in deducted: restore_stock(sb_admin, pid, qty, "fail_db")
        raise HTTPException(500, "Order creation failed (Database Error)")
    except Exception as e:
        for pid, qty in deducted: restore_stock(sb_admin, pid, qty, "fail_sys")
        raise HTTPException(500, "Order creation failed (System Error)")

    full = repo.get_order_by_id(order["id"])
    result = _sanitize_order(full if full else order)

    # 7. Event Dispatch
    try:
        get_event_bus().publish(OrderCreatedEvent(order=result, customer_email=current["profile"]["email"], customer_id=user_id))
    except Exception as e: logger.warning("Event failed: %s", e)

    return result

# ══════════════════════════════════════════════════════════════════════════════
#  GET /orders/my & GET /orders/my/{order_id}
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/my", response_model=OrderListResponse)
def my_orders(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status_filter: str | None = Query(None), current: dict[str, Any] = Depends(get_current_user)):
    if status_filter and status_filter not in VALID_STATUSES: 
        raise HTTPException(400, f"Invalid status: {status_filter}")
        
    items, total = OrderRepository().get_user_orders(current["profile"]["id"], status_filter, page, page_size)
    return {"items": _sanitize_order_list(items), "total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size) if page_size > 0 else 0}

@router.get("/my/{order_id}")
def get_my_order(request: Request, order_id: UUID, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    order = OrderRepository().get_order_by_id(str(order_id), current["profile"]["id"])
    if not order: raise HTTPException(404, "Order not found")
    return _sanitize_order(order)

@router.post("/my/{order_id}/cancel")
def cancel_order(request: Request, order_id: UUID, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    repo = OrderRepository()
    order = repo.get_order_by_id(str(order_id), current["profile"]["id"])
    if not order: raise HTTPException(404, "Order not found")
    if order["status"] != "pending": raise HTTPException(409, f"Cannot cancel '{order['status']}' order")

    updated = repo.update_order_status_safe(str(order_id), {"status": "cancelled"}, "pending")
    if not updated: raise HTTPException(409, "Order status could not be changed or is already updated")

    sb_admin = get_admin_supabase()
    for item in order.get("order_items", []):
        if item.get("product_id"): restore_stock(sb_admin, item["product_id"], item["quantity"], f"cancel:{order_id}")

    return {"status": "cancelled", "order_id": str(order_id)}

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/", dependencies=[Depends(require_admin)], response_model=OrderListResponse)
def list_all_orders(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status_filter: str | None = None):
    if status_filter and status_filter not in VALID_STATUSES: 
        raise HTTPException(400, "Invalid status")

    items, total = OrderRepository().get_all_orders(status_filter, page, page_size)
    return {"items": _sanitize_order_list(items), "total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size) if page_size > 0 else 0}

@router.patch("/{order_id}", dependencies=[Depends(require_admin)])
def admin_update_order(request: Request, order_id: UUID, payload: OrderAdminUpdate) -> dict[str, Any]:
    repo = OrderRepository()
    current_res = repo.get_order_for_admin_update(str(order_id))
    if not current_res: raise HTTPException(404, "Order not found")

    current_status = current_res["status"]

    if payload.status:
        allowed = STATUS_TRANSITIONS.get(current_status, set())
        if payload.status not in allowed: raise HTTPException(409, f"Cannot move '{current_status}' → '{payload.status}'")
            
        if payload.status == "refunded":
            pi_id = current_res.get("stripe_payment_intent")
            if pi_id:
                try:
                    payment_service = get_payment_provider("stripe")
                    payment_service.process_refund(pi_id)
                except Exception as e:
                    raise HTTPException(502, f"Refund failed: {e}")

    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    result = repo.update_order_status_safe(str(order_id), data, current_status)
    if not result: raise HTTPException(409, "Order modified — refresh and retry")

    # Events Dispatch
    if payload.status == "shipped":
        try:
            email = repo.get_user_email(current_res["customer_id"])
            if email: get_event_bus().publish(OrderShippedEvent(order=result, customer_email=email, customer_id=current_res["customer_id"], tracking_number=payload.tracking_number))
        except Exception: pass
    if payload.status in ("delivered", "refunded"):
        try: get_event_bus().publish(OrderStatusChangedEvent(order=result, customer_id=current_res["customer_id"], old_status=current_status, new_status=payload.status))
        except Exception: pass

    return _sanitize_order(result)