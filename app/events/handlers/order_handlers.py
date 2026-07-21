"""
Order Event Handlers (Hooks)
============================
Path: app/hooks/handlers/order_handlers.py

Contains all application reactions to order-related events.
"""
import os
import logging
from typing import Any

from app.services.events import (
    OrderCreatedEvent, OrderPaidEvent, OrderFailedEvent, 
    OrderShippedEvent, OrderStatusChangedEvent, LowStockEvent
)
from app.integrations.email.registry import get_email_provider
from app.integrations.push.webpush_impl import send_push_to_user, broadcast_push_to_admins

logger = logging.getLogger(__name__)

_ICON_BASE: str = os.environ.get("PUSH_ICON_BASE_URL", "/icons").rstrip("/")

class _Icon:
    NEW_ORDER = f"{_ICON_BASE}/ri-shopping-bag-3.png"
    PAID      = f"{_ICON_BASE}/ri-checkbox-circle.png"
    FAILED    = f"{_ICON_BASE}/ri-close-circle.png"
    CANCELLED = f"{_ICON_BASE}/ri-forbid-2.png"
    SHIPPED   = f"{_ICON_BASE}/ri-truck.png"
    DELIVERED = f"{_ICON_BASE}/ri-mail-check.png"
    REFUNDED  = f"{_ICON_BASE}/ri-refund-2.png"
    LOW_STOCK = f"{_ICON_BASE}/ri-alert.png"

class _Copy:
    URL_ORDERS = "/orders.html"
    URL_CART   = "/cart.html"  # 🔥 Added for failed payments
    URL_ADMIN  = "/admin.html"
    ADMIN_ORDER_TITLE   = "New Order #{oid}"
    ADMIN_ORDER_BODY    = "₹{amt} — needs processing"
    PAID_PUSH_TITLE     = "Payment Confirmed ✓"
    PAID_PUSH_BODY      = "Order #{oid} confirmed. We're preparing it now."
    FAILED_PUSH_TITLE   = "Payment Failed — Order #{oid}"
    FAILED_PUSH_BODY    = "Your payment could not be processed. Please try again."
    CANCEL_PUSH_TITLE   = "Order #{oid} Cancelled"
    CANCEL_PUSH_BODY    = "Your order was successfully cancelled."
    SHIPPED_PUSH_TITLE  = "Order #{oid} Shipped!"
    SHIPPED_PUSH_BODY   = "Your order is on the way."
    SHIPPED_TRACKING    = " Tracking: {tracking}"
    DELIVERED_TITLE     = "Order #{oid} Delivered!"
    DELIVERED_BODY      = "Your order has arrived. Enjoy!"
    REFUNDED_TITLE      = "Refund Initiated — Order #{oid}"
    REFUNDED_BODY       = "Your refund has been processed."
    LOW_STOCK_TITLE     = "Low Stock — {name}"
    LOW_STOCK_BODY      = "Only {stock} left (threshold: {threshold})"

def _safe_oid(order: dict[str, Any]) -> str:
    return str(order.get("id", "UNKNOWN"))[:8].upper()

# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_new_order_admin_push(event: OrderCreatedEvent) -> None:
    oid = _safe_oid(event.order or {})
    amt = (event.order or {}).get("total_amount", 0)
    await broadcast_push_to_admins(
        title=_Copy.ADMIN_ORDER_TITLE.format(oid=oid),
        body=_Copy.ADMIN_ORDER_BODY.format(amt=amt),
        icon=_Icon.NEW_ORDER,
        url=_Copy.URL_ADMIN
    )

async def handle_paid_email(event: OrderPaidEvent) -> None:
    if not event.customer_email or not event.order: return
    try:
        logger.info(f"[HOOK:EMAIL] Triggering Payment Success Email for {event.customer_email}")
        email_provider = get_email_provider("resend")
        await email_provider.send_payment_success(event.customer_email, event.order)
    except Exception as e:
        logger.error(f"[HOOK:EMAIL] Failed to send payment email: {e}", exc_info=True)

async def handle_paid_push(event: OrderPaidEvent) -> None:
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    if uid:
        await send_push_to_user(
            uid,
            title=_Copy.PAID_PUSH_TITLE, 
            body=_Copy.PAID_PUSH_BODY.format(oid=_safe_oid(order)),
            icon=_Icon.PAID, 
            url=_Copy.URL_ORDERS
        )

async def handle_failed_push(event: OrderFailedEvent) -> None:
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    if not uid: return
    
    raw_id = str(order.get("id", ""))
    is_cart = "SESSION" in raw_id
    oid = _safe_oid(order)
    
    # 🔥 Smart Title Logic for Checkout Sessions
    if is_cart:
        base_title = "Checkout Failed ❌"
    else:
        base_title = _Copy.FAILED_PUSH_TITLE.format(oid=oid)
    
    if event.reason == "payment_canceled":
        title = "Payment Cancelled" if is_cart else _Copy.CANCEL_PUSH_TITLE.format(oid=oid)
        body = "Your payment was cancelled. Your items are safely saved in your cart."
        icon = _Icon.CANCELLED
    elif event.reason == "payment_failed":
        title = base_title
        body = _Copy.FAILED_PUSH_BODY
        icon = _Icon.FAILED
    else:
        title = base_title
        body = str(event.reason)[:200]
        icon = _Icon.FAILED
    
    logger.info(f"[HOOK:PUSH] Sending Failed Push to {uid}: {title}")
    # 🔥 Changed URL to CART instead of ORDERS so user can retry
    await send_push_to_user(uid, title=title, body=body, icon=icon, url=_Copy.URL_CART)

async def handle_shipped_push(event: OrderShippedEvent) -> None:
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    if not uid: return
    body = _Copy.SHIPPED_PUSH_BODY
    if event.tracking_number: body += _Copy.SHIPPED_TRACKING.format(tracking=event.tracking_number)
    
    await send_push_to_user(
        uid,
        title=_Copy.SHIPPED_PUSH_TITLE.format(oid=_safe_oid(order)), body=body,
        icon=_Icon.SHIPPED, url=_Copy.URL_ORDERS
    )

async def handle_status_push(event: OrderStatusChangedEvent) -> None:
    _CONFIG = {
        "delivered": (_Copy.DELIVERED_TITLE, _Copy.DELIVERED_BODY, _Icon.DELIVERED),
        "refunded":  (_Copy.REFUNDED_TITLE,  _Copy.REFUNDED_BODY,  _Icon.REFUNDED),
        "cancelled": (_Copy.CANCEL_PUSH_TITLE, _Copy.CANCEL_PUSH_BODY, _Icon.CANCELLED),
    }
    cfg = _CONFIG.get(event.new_status)
    if not cfg: return
    
    title_tpl, body, icon = cfg
    await send_push_to_user(
        event.customer_id,
        title=title_tpl.format(oid=_safe_oid(event.order or {})), body=body,
        icon=icon, url=_Copy.URL_ORDERS
    )

async def handle_low_stock_push(event: LowStockEvent) -> None:
    await broadcast_push_to_admins(
        title=_Copy.LOW_STOCK_TITLE.format(name=event.product_name),
        body=_Copy.LOW_STOCK_BODY.format(stock=event.stock, threshold=event.threshold),
        icon=_Icon.LOW_STOCK, url=_Copy.URL_ADMIN
    )