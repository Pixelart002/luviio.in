"""
Event Bus  —  Observer Pattern
================================
Notification routing matrix:

  Trigger            | Customer              | Admin
  ───────────────────┼───────────────────────┼─────────────────
  Order created      | —                     | Push
  Order paid    ✅   | Email + Push          | —
  Order failed  ❌   | Push                  | —
  Order shipped 📦   | Push                  | —
  Status changed     | Push                  | —
  Low stock     ⚠️   | —                     | Push

Design notes:
  - Each handler owns exactly one notification channel + recipient.
  - All notification copy is declared as module-level constants — one
    place to update strings for the whole system.
  - EventBus guards against double-registration (safe on hot-reload and
    repeated lifespan calls during testing).
  - Lazy imports inside handlers avoid circular-import issues and keep
    startup time fast.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Notification copy  ────────────────────────────────────────────────────────
# Single source of truth.  Change strings here; nowhere else.

class _Copy:
    # Admin
    ADMIN_NEW_ORDER_TITLE = "New order received"
    ADMIN_LOW_STOCK_TITLE = "Low stock alert"

    # Customer — payment
    PAID_PUSH_TITLE   = "Payment confirmed"
    PAID_PUSH_BODY    = "Order #{oid} confirmed — ₹{amt}. We're preparing your order."
    FAILED_PUSH_TITLE = "Payment failed — Order #{oid}"
    FAILED_PUSH_BODY  = "Your payment could not be processed. Please try again."
    CANCEL_PUSH_TITLE = "Payment canceled — Order #{oid}"
    CANCEL_PUSH_BODY  = "Your payment was canceled. Stock has been released."

    # Customer — shipping
    SHIPPED_PUSH_TITLE = "Your order has shipped"
    SHIPPED_PUSH_BODY  = "Order #{oid} is on its way!"
    SHIPPED_TRACK_BODY = "Order #{oid} is on its way! Tracking: {tracking}"

    # Customer — status changes (delivered / cancelled / refunded only)
    STATUS_COPY: dict[str, tuple[str, str]] = {
        "delivered": (
            "Order delivered",
            "Order #{oid} has been delivered. Enjoy!",
        ),
        "cancelled": (
            "Order cancelled",
            "Order #{oid} has been cancelled.",
        ),
        "refunded": (
            "Refund initiated",
            "A refund has been initiated for order #{oid}.",
        ),
    }

    # Deep-link paths
    URL_ORDERS = "/orders.html"
    URL_ADMIN  = "/admin.html"


# ── Event dataclasses  ────────────────────────────────────────────────────────

@dataclass
class OrderCreatedEvent:
    """Order placed — notify admin only.  Customer gets nothing at this stage."""
    order:          dict[str, Any]
    customer_email: str
    customer_id:    str = ""


@dataclass
class OrderPaidEvent:
    """Payment succeeded — notify customer via email + push."""
    order:          dict[str, Any]
    customer_email: str
    customer_id:    str = ""


@dataclass
class OrderFailedEvent:
    """Payment failed or canceled — notify customer via push."""
    order:          dict[str, Any]
    customer_email: str
    customer_id:    str = ""
    reason:         str = "payment_failed"   # "payment_failed" | "payment_canceled"


@dataclass
class OrderShippedEvent:
    """Order shipped — notify customer via push."""
    order:           dict[str, Any]
    customer_email:  str
    customer_id:     str = ""
    tracking_number: str | None = None


@dataclass
class OrderStatusChangedEvent:
    """Generic status transition — push customer for delivered/cancelled/refunded."""
    order:       dict[str, Any]
    customer_id: str
    old_status:  str
    new_status:  str


@dataclass
class LowStockEvent:
    """Stock fell below threshold — push admins."""
    product_id:   str
    product_name: str
    stock:        int
    threshold:    int


# ── Event Bus  ────────────────────────────────────────────────────────────────

EventType = type
Handler   = Callable[[Any], None]


class EventBus:
    """
    In-process synchronous event bus.

    Swap `publish` for an async queue (Celery / ARQ) without touching any
    handler or router — just change this class.
    """

    def __init__(self) -> None:
        self._handlers:   dict[EventType, list[Handler]] = defaultdict(list)
        self._registered: bool = False

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        for handler in self._handlers[type(event)]:
            try:
                handler(event)
            except Exception as exc:
                logger.error(
                    "Handler %s failed for %s: %s",
                    handler.__name__, type(event).__name__, exc,
                )

    def reset(self) -> None:
        """Testing only — clear all handlers and reset the registration flag."""
        self._handlers.clear()
        self._registered = False


_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


# ── Internal push helpers  ────────────────────────────────────────────────────
# Centralise all error handling so individual handlers stay clean.

def _safe_oid(order: dict[str, Any]) -> str:
    """Return an 8-char upper-cased order ID fragment, never raises."""
    return str(order.get("id", "UNKNOWN"))[:8].upper()


def _push_user(sb: Any, user_id: str, *, title: str, body: str, url: str) -> None:
    from app.utils.push import send_push_to_user
    try:
        send_push_to_user(sb, user_id=user_id, title=title, body=body, url=url)
    except Exception as exc:
        logger.warning("send_push_to_user failed | user=%.8s | %s", user_id, exc)


def _push_admins(sb: Any, *, title: str, body: str, url: str) -> None:
    from app.utils.push import broadcast_push_to_admins
    try:
        broadcast_push_to_admins(sb, title=title, body=body, url=url)
    except Exception as exc:
        logger.warning("broadcast_push_to_admins failed: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS — one function = one notification
# ══════════════════════════════════════════════════════════════════════════════

# ── Admin: new order ──────────────────────────────────────────────────────────

def _push_new_order_admin(event: OrderCreatedEvent) -> None:
    """Push admins the moment an order is placed.  Customer gets nothing yet."""
    from app.supabase_client import get_admin_supabase
    sb    = get_admin_supabase()
    order = event.order or {}
    oid   = _safe_oid(order)
    amt   = order.get("total_amount", 0)

    _push_admins(
        sb,
        title=_Copy.ADMIN_NEW_ORDER_TITLE,
        body=f"Order #{oid} — ₹{amt}",
        url=_Copy.URL_ADMIN,
    )


# ── Customer: payment confirmed — email ───────────────────────────────────────

def _email_order_confirmation(event: OrderPaidEvent) -> None:
    """
    Send the confirmation email only after payment succeeds — not on order-create.
    Non-fatal: a failed email must not roll back a paid order.
    """
    if not event.order:
        logger.warning("OrderPaidEvent has no order data — skipping confirmation email")
        return

    from app.utils.email import send_order_confirmation
    try:
        send_order_confirmation(event.customer_email, event.order)
    except Exception as exc:
        logger.error("Confirmation email failed | to=%s | %s", event.customer_email, exc)


# ── Customer: payment confirmed — push ────────────────────────────────────────

def _push_order_paid(event: OrderPaidEvent) -> None:
    """Push the customer immediately after payment succeeds."""
    from app.supabase_client import get_admin_supabase
    sb    = get_admin_supabase()
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")

    if not uid:
        logger.warning("_push_order_paid: no customer_id — skipping push")
        return

    oid = _safe_oid(order)
    amt = order.get("total_amount", 0)

    _push_user(
        sb, uid,
        title=_Copy.PAID_PUSH_TITLE,
        body=_Copy.PAID_PUSH_BODY.format(oid=oid, amt=amt),
        url=_Copy.URL_ORDERS,
    )


# ── Customer: payment failed / canceled ───────────────────────────────────────

def _push_order_failed(event: OrderFailedEvent) -> None:
    """Push the customer when their payment is rejected or canceled."""
    from app.supabase_client import get_admin_supabase
    sb    = get_admin_supabase()
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")

    if not uid:
        logger.warning("_push_order_failed: no customer_id — skipping push")
        return

    oid = _safe_oid(order)

    if event.reason == "payment_canceled":
        title = _Copy.CANCEL_PUSH_TITLE.format(oid=oid)
        body  = _Copy.CANCEL_PUSH_BODY
    else:
        title = _Copy.FAILED_PUSH_TITLE.format(oid=oid)
        body  = _Copy.FAILED_PUSH_BODY

    _push_user(sb, uid, title=title, body=body, url=_Copy.URL_ORDERS)


# ── Customer: order shipped ───────────────────────────────────────────────────

def _push_order_shipped(event: OrderShippedEvent) -> None:
    """Push the customer when their order ships."""
    from app.supabase_client import get_admin_supabase
    sb    = get_admin_supabase()
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")

    if not uid:
        logger.warning("_push_order_shipped: no customer_id — skipping push")
        return

    oid  = _safe_oid(order)
    body = (
        _Copy.SHIPPED_TRACK_BODY.format(oid=oid, tracking=event.tracking_number)
        if event.tracking_number
        else _Copy.SHIPPED_PUSH_BODY.format(oid=oid)
    )

    _push_user(
        sb, uid,
        title=_Copy.SHIPPED_PUSH_TITLE,
        body=body,
        url=_Copy.URL_ORDERS,
    )


# ── Customer: generic status change ───────────────────────────────────────────

def _push_order_status(event: OrderStatusChangedEvent) -> None:
    """
    Push the customer for terminal status changes.
    'paid'    is excluded — handled by OrderPaidEvent.
    'shipped' is excluded — handled by OrderShippedEvent.
    """
    copy = _Copy.STATUS_COPY.get(event.new_status)
    if not copy:
        return

    from app.supabase_client import get_admin_supabase
    sb    = get_admin_supabase()
    order = event.order or {}
    oid   = _safe_oid(order)

    title, body = copy[0], copy[1].format(oid=oid)
    _push_user(sb, event.customer_id, title=title, body=body, url=_Copy.URL_ORDERS)


# ── Admin: low stock ──────────────────────────────────────────────────────────

def _push_low_stock(event: LowStockEvent) -> None:
    """Push admins when a product's stock falls below its threshold."""
    from app.supabase_client import get_admin_supabase
    sb = get_admin_supabase()

    _push_admins(
        sb,
        title=_Copy.ADMIN_LOW_STOCK_TITLE,
        body=(
            f"{event.product_name} — {event.stock} units left"
            f" (threshold: {event.threshold})"
        ),
        url=_Copy.URL_ADMIN,
    )


# ── Handler registration ──────────────────────────────────────────────────────

def register_default_handlers() -> None:
    """
    Wire all handlers to their event types.

    Called once at app startup via lifespan.
    Guarded against double-registration — safe on hot-reload and in tests.
    """
    bus = get_event_bus()

    if bus._registered:
        logger.warning("register_default_handlers called more than once — skipping")
        return

    bus.subscribe(OrderCreatedEvent,       _push_new_order_admin)

    bus.subscribe(OrderPaidEvent,          _email_order_confirmation)
    bus.subscribe(OrderPaidEvent,          _push_order_paid)

    bus.subscribe(OrderFailedEvent,        _push_order_failed)

    bus.subscribe(OrderShippedEvent,       _push_order_shipped)

    bus.subscribe(OrderStatusChangedEvent, _push_order_status)

    bus.subscribe(LowStockEvent,           _push_low_stock)

    bus._registered = True

    logger.info(
        "Event handlers registered | "
        "OrderCreated→AdminPush | "
        "OrderPaid→CustomerEmail+Push | "
        "OrderFailed→CustomerPush | "
        "OrderShipped→CustomerPush | "
        "StatusChanged→CustomerPush | "
        "LowStock→AdminPush"
    )