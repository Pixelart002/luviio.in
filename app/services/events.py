"""
Event Bus — Observer Pattern + Notification Router
===================================================
FIX: Handlers ab background thread mein chalte hain.
     Request thread block nahi hota — push late delivery fix.

Notification Matrix:
  ┌──────────────────────┬──────────────────────┬──────────────────────┐
  │ Event                │ Customer             │ Admin                │
  ├──────────────────────┼──────────────────────┼──────────────────────┤
  │ OrderCreatedEvent    │ —                    │ Push                 │
  │ OrderPaidEvent       │ Email + Push         │ —                    │
  │ OrderFailedEvent     │ Push (Stripe error)  │ —                    │
  │ OrderShippedEvent    │ Push                 │ —                    │
  │ OrderStatusChanged   │ Push (status-icon)   │ —                    │
  │ LowStockEvent        │ —                    │ Push                 │
  └──────────────────────┴──────────────────────┴──────────────────────┘
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from app.utils.push  import send_push_to_user, broadcast_push_to_admins
from app.utils.email import send_order_confirmation

logger = logging.getLogger(__name__)

__all__ = [
    "EventBus", "get_event_bus", "register_default_handlers",
    "OrderCreatedEvent", "OrderPaidEvent", "OrderFailedEvent",
    "OrderShippedEvent", "OrderStatusChangedEvent", "LowStockEvent",
]

# Background thread pool — handlers run here, not in request thread
# max_workers=4: 4 push jobs parallel; tune as needed
_handler_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="event-handler")

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
    URL_ADMIN  = "/admin.html"

    ADMIN_ORDER_TITLE   = "New Order #{oid}"
    ADMIN_ORDER_BODY    = "₹{amt} — needs processing"

    PAID_PUSH_TITLE     = "Payment Confirmed ✓"
    PAID_PUSH_BODY      = "Order #{oid} confirmed. We're preparing it now."

    FAILED_PUSH_TITLE   = "Payment Failed — Order #{oid}"
    FAILED_PUSH_BODY    = "Your payment could not be processed. Please try again."

    CANCEL_PUSH_TITLE   = "Order #{oid} Cancelled"
    CANCEL_PUSH_BODY    = "Your payment was cancelled. Items are still in your cart."

    SHIPPED_PUSH_TITLE  = "Order #{oid} Shipped!"
    SHIPPED_PUSH_BODY   = "Your order is on the way."
    SHIPPED_TRACKING    = " Tracking: {tracking}"

    DELIVERED_TITLE     = "Order #{oid} Delivered!"
    DELIVERED_BODY      = "Your order has arrived. Enjoy!"
    REFUNDED_TITLE      = "Refund Initiated — Order #{oid}"
    REFUNDED_BODY       = "Your refund has been processed."

    LOW_STOCK_TITLE     = "Low Stock — {name}"
    LOW_STOCK_BODY      = "Only {stock} left (threshold: {threshold})"


# ── Event Dataclasses ─────────────────────────────────────────────────────────

@dataclass
class OrderCreatedEvent:
    order:          dict[str, Any]
    customer_email: str
    customer_id:    str = ""

@dataclass
class OrderPaidEvent:
    order:          dict[str, Any]
    customer_email: str
    customer_id:    str = ""

@dataclass
class OrderFailedEvent:
    order:          dict[str, Any]
    customer_email: str
    customer_id:    str = ""
    reason:         str = "payment_failed"

@dataclass
class OrderShippedEvent:
    order:           dict[str, Any]
    customer_email:  str
    customer_id:     str = ""
    tracking_number: str | None = None

@dataclass
class OrderStatusChangedEvent:
    order:       dict[str, Any]
    customer_id: str
    old_status:  str
    new_status:  str

@dataclass
class LowStockEvent:
    product_id:   str
    product_name: str
    stock:        int
    threshold:    int


# ── Event Bus ─────────────────────────────────────────────────────────────────

EventType = type
Handler   = Callable[[Any], None]


class EventBus:
    """
    FIX: publish() ab handlers ko background thread mein submit karta hai.
    Request thread turant return karta hai — push delivery se HTTP response
    block nahi hota.

    Scaling path: ThreadPoolExecutor ko Celery/ARQ/RQ se replace karo
    bina call sites change kiye.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        """
        Har handler ko background thread pool mein submit karo.
        Request thread block nahi hota.
        """
        for handler in self._handlers[type(event)]:
            _handler_pool.submit(_run_handler, handler, event)


def _run_handler(handler: Handler, event: Any) -> None:
    """Background thread mein handler safely chalao."""
    try:
        handler(event)
    except Exception as exc:
        logger.error(
            "Handler %s raised for %s: %s",
            handler.__name__, type(event).__name__, exc,
        )


_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_oid(order: dict[str, Any]) -> str:
    return str(order.get("id", "UNKNOWN"))[:8].upper()


def _push_user(sb, user_id: str, *, title: str, body: str, icon: str,
               url: str = _Copy.URL_ORDERS) -> None:
    if not user_id:
        logger.warning("_push_user: empty user_id — skipping")
        return
    send_push_to_user(sb, user_id, title=title, body=body, icon=icon, url=url)


def _push_admins(sb, *, title: str, body: str, icon: str,
                 url: str = _Copy.URL_ADMIN) -> None:
    broadcast_push_to_admins(sb, title=title, body=body, icon=icon, url=url)


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_new_order_admin_push(event: OrderCreatedEvent) -> None:
    from app.supabase_client import get_admin_supabase
    oid = _safe_oid(event.order or {})
    amt = (event.order or {}).get("total_amount", 0)
    _push_admins(
        get_admin_supabase(),
        title=_Copy.ADMIN_ORDER_TITLE.format(oid=oid),
        body=_Copy.ADMIN_ORDER_BODY.format(amt=amt),
        icon=_Icon.NEW_ORDER,
    )


def _handle_paid_email(event: OrderPaidEvent) -> None:
    if not event.customer_email or not event.order:
        logger.warning("_handle_paid_email: missing data — skipping")
        return
    send_order_confirmation(event.customer_email, event.order)


def _handle_paid_push(event: OrderPaidEvent) -> None:
    from app.supabase_client import get_admin_supabase
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")
    _push_user(
        get_admin_supabase(), uid,
        title=_Copy.PAID_PUSH_TITLE,
        body=_Copy.PAID_PUSH_BODY.format(oid=_safe_oid(order)),
        icon=_Icon.PAID,
    )


def _handle_failed_push(event: OrderFailedEvent) -> None:
    from app.supabase_client import get_admin_supabase
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")
    if not uid:
        logger.warning("_handle_failed_push: no customer_id — skipping")
        return
    oid = _safe_oid(order)
    if event.reason == "payment_canceled":
        title, body, icon = _Copy.CANCEL_PUSH_TITLE.format(oid=oid), _Copy.CANCEL_PUSH_BODY, _Icon.CANCELLED
    elif event.reason == "payment_failed":
        title, body, icon = _Copy.FAILED_PUSH_TITLE.format(oid=oid), _Copy.FAILED_PUSH_BODY, _Icon.FAILED
    else:
        title, body, icon = _Copy.FAILED_PUSH_TITLE.format(oid=oid), event.reason, _Icon.FAILED
    _push_user(get_admin_supabase(), uid, title=title, body=body, icon=icon)


def _handle_shipped_push(event: OrderShippedEvent) -> None:
    from app.supabase_client import get_admin_supabase
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")
    body  = _Copy.SHIPPED_PUSH_BODY
    if event.tracking_number:
        body += _Copy.SHIPPED_TRACKING.format(tracking=event.tracking_number)
    _push_user(
        get_admin_supabase(), uid,
        title=_Copy.SHIPPED_PUSH_TITLE.format(oid=_safe_oid(order)),
        body=body, icon=_Icon.SHIPPED,
    )


def _handle_status_push(event: OrderStatusChangedEvent) -> None:
    _CONFIG = {
        "delivered": (_Copy.DELIVERED_TITLE, _Copy.DELIVERED_BODY, _Icon.DELIVERED),
        "refunded":  (_Copy.REFUNDED_TITLE,  _Copy.REFUNDED_BODY,  _Icon.REFUNDED),
    }
    cfg = _CONFIG.get(event.new_status)
    if not cfg:
        return
    from app.supabase_client import get_admin_supabase
    title_tpl, body, icon = cfg
    _push_user(
        get_admin_supabase(), event.customer_id,
        title=title_tpl.format(oid=_safe_oid(event.order or {})),
        body=body, icon=icon,
    )


def _handle_low_stock_push(event: LowStockEvent) -> None:
    from app.supabase_client import get_admin_supabase
    _push_admins(
        get_admin_supabase(),
        title=_Copy.LOW_STOCK_TITLE.format(name=event.product_name),
        body=_Copy.LOW_STOCK_BODY.format(stock=event.stock, threshold=event.threshold),
        icon=_Icon.LOW_STOCK,
    )


# ── Registration ──────────────────────────────────────────────────────────────

_registered: bool = False


def register_default_handlers() -> None:
    """Idempotent — safe for hot-reload and tests."""
    global _registered
    if _registered:
        logger.debug("register_default_handlers: already registered — skipping")
        return

    bus = get_event_bus()
    bus.subscribe(OrderCreatedEvent,       _handle_new_order_admin_push)
    bus.subscribe(OrderPaidEvent,          _handle_paid_email)
    bus.subscribe(OrderPaidEvent,          _handle_paid_push)
    bus.subscribe(OrderFailedEvent,        _handle_failed_push)
    bus.subscribe(OrderShippedEvent,       _handle_shipped_push)
    bus.subscribe(OrderStatusChangedEvent, _handle_status_push)
    bus.subscribe(LowStockEvent,           _handle_low_stock_push)

    _registered = True
    logger.info(
        "Event handlers registered | "
        "OrderCreated→AdminPush | OrderPaid→CustomerEmail+Push | "
        "OrderFailed→CustomerPush(+StripeError) | OrderShipped→CustomerPush | "
        "OrderStatus→CustomerPush | LowStock→AdminPush"
    )
