"""
Orders Router
=============
Path: app/api/v1/routers/orders.py

Architecture notes:
  1. All Supabase DB logic is strictly asynchronous (await).
  2. Order creation is handled exclusively by the JIT payment flow
     (POST /api/v1/payments/confirm). There is no direct POST /orders/ endpoint.
  3. Stripe refund calls are wrapped in run_in_threadpool to avoid blocking
     the async event loop.
  4. 🔥 ENTERPRISE FIX: Added `get_user_id_strict` for IDOR elimination.
  5. 🔥 OBSERVABILITY FIX: Saturated all self-fetch and admin overrides with PureWindowLogger hooks.

IMPORTANT — _sanitize_order / _sanitize_order_list:
  These helpers perform pure in-memory dict transformation (no I/O).
  They MUST remain plain synchronous `def` functions.
  Marking them `async def` without awaiting them at every call site causes
  FastAPI to receive a coroutine object instead of a dict, triggering a
  ResponseValidationError (see PYTHON-FASTAPI-C).
"""
import logging
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool  # 🔥 IMPORT ADDED FOR STRIPE REFUND FIX
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 SECURITY UPDATE: Added get_user_id_strict
from app.core.dependencies import get_current_user, get_user_id_strict, require_admin
from app.api.schemas.order_dto import OrderAdminUpdate, VALID_STATUSES, OrderListResponse
from app.repositories.order_repo import AsyncOrderRepository
from app.services.events import get_event_bus, OrderShippedEvent, OrderStatusChangedEvent
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


@router.get("/my", response_model=OrderListResponse)
async def my_orders(
    request: Request, 
    page: int = Query(1, ge=1), 
    page_size: int = Query(20, ge=1, le=100), 
    status_filter: str | None = Query(None), 
    user_id: str = Depends(get_user_id_strict) # 🔥 ABAC ZERO-IDOR GUARD
):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"ABAC Scoped Fetch -> Target UID: {user_id[:8]}... (Page: {page})")

    # user_id = current["profile"]["id"] <-- REPLACED
    logger.info(f"[ORDERS] User {user_id} fetching their orders (Page: {page}, Filter: {status_filter})")
    
    if status_filter and status_filter not in VALID_STATUSES: 
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"❌ Aborted: Invalid status filter requested ('{status_filter}')")
        logger.warning(f"[ORDERS] Invalid status filter requested: {status_filter}")
        raise HTTPException(400, "Invalid status")
        
    repo = AsyncOrderRepository()
    items, total = await repo.get_user_orders(user_id, status_filter, page, page_size)

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Retrieved {len(items)} orders -> Executing fast in-memory dict sanitization")

    return {"items": _sanitize_order_list(items), "total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size) if page_size > 0 else 0}

@router.get("/my/{order_id}")
async def get_my_order(
    request: Request, 
    order_id: UUID, 
    user_id: str = Depends(get_user_id_strict) # 🔥 ABAC ZERO-IDOR GUARD
) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Targeting Order details for ID: {str(order_id)[:8]}...")

    # user_id = current["profile"]["id"] <-- REPLACED
    logger.info(f"[ORDERS] User {user_id} requesting order details for {order_id}")
    
    repo = AsyncOrderRepository()
    order = await repo.get_order_by_id(str(order_id), user_id)
    if not order: 
        if hasattr(request.state, "actions"):
            request.state.actions.append("❌ Aborted: Order not found or does not belong to active user")
        logger.warning(f"[ORDERS] Order {order_id} not found or denied for user {user_id}")
        raise HTTPException(404, "Order not found")
        
    if hasattr(request.state, "actions"):
        request.state.actions.append("Order ownership verified -> Stripping internal payment metadata")

    return _sanitize_order(order)

@router.post("/my/{order_id}/cancel")
async def cancel_order(
    request: Request, 
    order_id: UUID, 
    user_id: str = Depends(get_user_id_strict) # 🔥 ABAC ZERO-IDOR GUARD
) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating Cancellation sequence for Order: {str(order_id)[:8]}...")

    # user_id = current["profile"]["id"] <-- REPLACED
    logger.info(f"[ORDERS] User {user_id} requesting cancellation for order {order_id}")
    
    repo = AsyncOrderRepository()
    updated = await repo.cancel_order_and_restore_stock(str(order_id), user_id)
    
    if not updated: 
        if hasattr(request.state, "actions"):
            request.state.actions.append("❌ Aborted: Order is no longer in 'pending' or 'paid' state")
        logger.warning(f"[ORDERS] Cannot cancel order {order_id} for user {user_id} (Invalid state)")
        raise HTTPException(409, "Cannot cancel this order (it might not be pending)")

    if hasattr(request.state, "actions"):
        request.state.actions.append("Order marked Cancelled -> Stock rolled back successfully")

    try:
        logger.info(f"[ORDERS] Publishing OrderStatusChangedEvent for cancelled order {order_id}")
        get_event_bus().publish(OrderStatusChangedEvent(
            order=updated, customer_id=user_id, 
            old_status="pending", new_status="cancelled"
        ))
        if hasattr(request.state, "actions"):
            request.state.actions.append("Dispatched background cancellation reaction hooks")
    except Exception as e:
        logger.error(f"[ORDERS] Failed to publish cancellation event for {order_id}: {e}")

    return {"status": "cancelled", "order_id": str(order_id)}

@router.get("/", dependencies=[Depends(require_admin)], response_model=OrderListResponse)
async def list_all_orders(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status_filter: str | None = None):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"God-Mode: Admin fetching global order ledger (Page: {page})")

    logger.info(f"[ORDERS:ADMIN] Admin fetching all orders (Page: {page}, Filter: {status_filter})")
    
    if status_filter and status_filter not in VALID_STATUSES: 
        logger.warning(f"[ORDERS:ADMIN] Invalid status filter requested: {status_filter}")
        raise HTTPException(400, "Invalid status")
        
    repo = AsyncOrderRepository()
    items, total = await repo.get_all_orders(status_filter, page, page_size)
    return {"items": _sanitize_order_list(items), "total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size) if page_size > 0 else 0}

@router.patch("/{order_id}", dependencies=[Depends(require_admin)])
async def admin_update_order(request: Request, order_id: UUID, payload: OrderAdminUpdate) -> dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin overriding state for Order: {str(order_id)[:8]}...")

    logger.info(f"[ORDERS:ADMIN] Admin updating order {order_id} with payload: {payload.model_dump(exclude_unset=True)}")
    
    repo = AsyncOrderRepository()
    current_res = await repo.get_order_for_admin_update(str(order_id))
    if not current_res: 
        raise HTTPException(404, "Order not found")

    current_status = current_res["status"]

    if payload.status:
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Attempting transition: '{current_status}' -> '{payload.status}'")

        allowed = STATUS_TRANSITIONS.get(current_status, set())
        if payload.status not in allowed: 
            if hasattr(request.state, "actions"):
                request.state.actions.append("❌ Aborted: State transition violates hardcoded DAG rules")
            raise HTTPException(409, f"Cannot move '{current_status}' → '{payload.status}'")
            
        if payload.status == "refunded":
            pi_id = current_res.get("stripe_payment_intent")
            if pi_id:
                if hasattr(request.state, "actions"):
                    request.state.actions.append(f"Offloading synchronous Stripe Refund ({pi_id[:8]}...) to Threadpool")
                logger.info(f"[ORDERS:ADMIN] Processing Stripe Refund for Payment Intent: {pi_id}")
                try: 
                    # 🔥 CRITICAL FIX: Wrapped synchronous Stripe call in threadpool
                    await run_in_threadpool(get_payment_provider("stripe").process_refund, pi_id)
                    logger.info(f"[ORDERS:ADMIN] Stripe refund processed successfully for {pi_id}")
                    if hasattr(request.state, "actions"):
                        request.state.actions.append("Stripe API confirmed refund success")
                except Exception as e: 
                    logger.error(f"[ORDERS:ADMIN] Stripe refund failed for {pi_id}: {e}", exc_info=True)
                    raise HTTPException(502, f"Refund failed: {e}")
        
        if payload.status == "cancelled":
            result = await repo.cancel_order_and_restore_stock(str(order_id))
            if not result: raise HTTPException(409, "Order cannot be cancelled")
        else:
            data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
            result = await repo.update_order_status_safe(str(order_id), data, current_status)
            if not result: raise HTTPException(409, "Order modified — refresh and retry")
    else:
        if hasattr(request.state, "actions"):
            request.state.actions.append("Committing tracking metadata notes without financial state shift")
        data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        result = await repo.update_order_status_safe(str(order_id), data, current_status)

    # Trigger events based on new status
    if payload.status == "shipped":
        try:
            email = await repo.get_user_email(current_res["customer_id"])
            if email: 
                get_event_bus().publish(OrderShippedEvent(order=result, customer_email=email, customer_id=current_res["customer_id"], tracking_number=payload.tracking_number))
                if hasattr(request.state, "actions"):
                    request.state.actions.append("Fired background OrderShipped dispatch hooks")
        except Exception as e: logger.error(f"[ORDERS:ADMIN] Failed to publish shipped event: {e}")
    
    if payload.status in ("delivered", "refunded", "cancelled"):
        try: 
            get_event_bus().publish(OrderStatusChangedEvent(order=result, customer_id=current_res["customer_id"], old_status=current_status, new_status=payload.status))
        except Exception as e: logger.error(f"[ORDERS:ADMIN] Failed to publish status changed event: {e}")

    return _sanitize_order(result)