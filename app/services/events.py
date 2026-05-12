"""
Event Bus — Observer Pattern + Notification Router
===================================================

Notification Matrix:
  ┌──────────────────────┬──────────────────────┬──────────────────────┐
  │ Event                │ Customer             │ Admin                │
  ├──────────────────────┼──────────────────────┼──────────────────────┤
  │ OrderCreatedEvent    │ —                    │ Push  (ri-bag-3)     │
  │ OrderPaidEvent       │ Email + Push         │ —                    │
  │ OrderFailedEvent     │ Push  (Stripe error) │ —                    │
  │ OrderShippedEvent    │ Push                 │ —                    │
  │ OrderStatusChanged   │ Push  (status-icon)  │ —                    │
  │ LowStockEvent        │ —                    │ Push  (ri-alert)     │
  └──────────────────────┴──────────────────────┴──────────────────────┘

Push icon paths follow Remix Icons naming (ri-*).
Set PUSH_ICON_BASE_URL env var to your CDN base URL.
Defaults to "/icons" (same-domain relative — works out of the box).

Design decisions:
  • register_default_handlers() is IDEMPOTENT — safe for hot-reload + tests.
  • send_push_to_user / broadcast / send_order_confirmation imported at module
    level → ImportError surfaces at startup, not on first notification.
  • get_admin_supabase() is called inside handlers at runtime because clients
    are initialised in lifespan(), after this module is first imported.
  • Notification failures are always non-fatal: a push/email error must never
    roll back or mask a successful payment.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

# Module-level imports — ImportError surfaces at startup, not at notification time
from app.utils.push  import send_push_to_user, broadcast_push_to_admins
from app.utils.email import send_order_confirmation

logger = logging.getLogger(__name__)

__all__ = [
    "EventBus",
    "get_event_bus",
    "register_default_handlers",
    "OrderCreatedEvent",
    "OrderPaidEvent",
    "OrderFailedEvent",
    "OrderShippedEvent",
    "OrderStatusChangedEvent",
    "LowStockEvent",
]


# ══════════════════════════════════════════════════════════════════════════════
#  ICON MAP  —  Remix Icons → push notification CDN paths
# ══════════════════════════════════════════════════════════════════════════════

_ICON_BASE: str = os.environ.get("PUSH_ICON_BASE_URL", "/icons").rstrip("/")


class _Icon:
    """
    Remix Icon filenames served from your CDN.
    Frontend uses ri-* CSS classes; backend sends these URLs in push payloads.
    """
    NEW_ORDER  = f"{_ICON_BASE}/ri-shopping-bag-3.png"   # ri-shopping-bag-3-fill
    PAID       = f"{_ICON_BASE}/ri-checkbox-circle.png"  # ri-checkbox-circle-fill
    FAILED     = f"{_ICON_BASE}/ri-close-circle.png"     # ri-close-circle-fill
    CANCELLED  = f"{_ICON_BASE}/ri-forbid-2.png"         # ri-forbid-2-fill
    SHIPPED    = f"{_ICON_BASE}/ri-truck.png"             # ri-truck-fill
    DELIVERED  = f"{_ICON_BASE}/ri-mail-check.png"       # ri-mail-check-fill
    REFUNDED   = f"{_ICON_BASE}/ri-refund-2.png"         # ri-refund-2-fill
    LOW_STOCK  = f"{_ICON_BASE}/ri-alert.png"            # ri-alert-fill


# ══════════════════════════════════════════════════════════════════════════════
#  COPY STRINGS  —  all user-facing strings in one place (easy to localise)
# ══════════════════════════════════════════════════════════════════════════════

class _Copy:
    """Notification copy. Use .format(oid=…, amt=…, …) for templating."""

    # Deep-link targets
    URL_ORDERS = "/orders.html"
    URL_ADMIN  = "/admin.html"

    # Admin — new order
    ADMIN_ORDER_TITLE = "New Order #{oid}"
    ADMIN_ORDER_BODY  = "₹{amt} — needs processing"

    # Customer — payment confirmed
    PAID_PUSH_TITLE = "Payment Confirmed ✓"
    PAID_PUSH_BODY  = "Order #{oid} confirmed. We're preparing it now."

    # Customer — payment failed (generic)
    FAILED_PUSH_TITLE = "Payment Failed — Order #{oid}"
    FAILED_PUSH_BODY  = "Your payment could not be processed. Please try again."

    # Customer — intent cancelled
    CANCEL_PUSH_TITLE = "Order #{oid} Cancelled"
    CANCEL_PUSH_BODY  = "Your payment was cancelled. Items are still in your cart."

    # Customer — shipped
    SHIPPED_PUSH_TITLE   = "Order #{oid} Shipped!"
    SHIPPED_PUSH_BODY    = "Your order is on the way."
    SHIPPED_TRACKING_SUF = " Tracking: {tracking}"

    # Customer — status transitions
    DELIVERED_TITLE = "Order #{oid} Delivered!"
    DELIVERED_BODY  = "Your order has arrived. Enjoy!"
    REFUNDED_TITLE  = "Refund Initiated — Order #{oid}"
    REFUNDED_BODY   = "Your refund has been processed."

    # Admin — low stock
    LOW_STOCK_TITLE = "Low Stock — {name}"
    LOW_STOCK_BODY  = "Only {stock} left (threshold: {threshold})"


# ══════════════════════════════════════════════════════════════════════════════
#  EVENT DATACLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class OrderCreatedEvent:
    """Order placed. Admin is notified. Customer notification comes on payment."""
    order:          dict[str, Any]
    customer_email: str
    customer_id:    str = ""


@dataclass
class OrderPaidEvent:
    """Payment succeeded. Send confirmation email + push to customer."""
    order:          dict[str, Any]
    customer_email: str
    customer_id:    str = ""


@dataclass
class OrderFailedEvent:
    """
    Payment failed or PaymentIntent was cancelled.

    `reason` semantics (set by payments router):
      "payment_canceled"   — Stripe intent was cancelled by user / timeout
      "payment_failed"     — generic failure (no Stripe message available)
      <any other string>   — verbatim Stripe last_payment_error.message
                             (e.g. "We are unable to authenticate your payment
                              method. Please choose a different payment method
                              and try again.")
                             Shown directly in the push body so the customer
                             knows exactly what went wrong.
    """
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
    """
    Fired by admin order-update for status transitions not covered by
    dedicated events. Handles: delivered, refunded.

    Intentionally NOT used for:
      "paid"      → OrderPaidEvent
      "shipped"   → OrderShippedEvent
      "cancelled" via payment failure → OrderFailedEvent
    """
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


# ══════════════════════════════════════════════════════════════════════════════
#  EVENT BUS
# ══════════════════════════════════════════════════════════════════════════════

EventType = type
Handler   = Callable[[Any], None]


class EventBus:
    """
    Synchronous in-process event bus.

    Scaling path: replace publish() body with a task queue (Celery, ARQ, RQ)
    without changing any call sites.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        for handler in self._handlers[type(event)]:
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


# ══════════════════════════════════════════════════════════════════════════════
#  PRIVATE PUSH HELPERS  —  single call site for every push action
# ══════════════════════════════════════════════════════════════════════════════

def _safe_oid(order: dict[str, Any]) -> str:
    """Return an 8-char uppercase display ID from an order dict."""
    return str(order.get("id", "UNKNOWN"))[:8].upper()


def _push_user(
    sb: Any,
    user_id: str,
    *,
    title: str,
    body: str,
    icon: str,
    url: str = _Copy.URL_ORDERS,
) -> None:
    """
    Push a notification to all subscriptions of one user.
    No-ops with a warning if user_id is empty.
    """
    if not user_id:
        logger.warning("_push_user: empty user_id — skipping")
        return
    send_push_to_user(sb, user_id, title=title, body=body, icon=icon, url=url)


def _push_admins(
    sb: Any,
    *,
    title: str,
    body: str,
    icon: str,
    url: str = _Copy.URL_ADMIN,
) -> None:
    """Push a notification to all active admin users."""
    broadcast_push_to_admins(sb, title=title, body=body, icon=icon, url=url)


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS  —  one function = one notification action
# ══════════════════════════════════════════════════════════════════════════════

def _handle_new_order_admin_push(event: OrderCreatedEvent) -> None:
    """
    Push admins when a new order is placed.
    Customer receives NOTHING at this stage — notification comes after payment.
    Remix icon: ri-shopping-bag-3-fill
    """
    from app.supabase_client import get_admin_supabase
    order = event.order or {}
    oid   = _safe_oid(order)
    amt   = order.get("total_amount", 0)

    _push_admins(
        get_admin_supabase(),
        title=_Copy.ADMIN_ORDER_TITLE.format(oid=oid),
        body=_Copy.ADMIN_ORDER_BODY.format(amt=amt),
        icon=_Icon.NEW_ORDER,
    )


def _handle_paid_email(event: OrderPaidEvent) -> None:
    """
    Send order-confirmation email to customer after payment succeeds.
    Remix icon: ri-checkbox-circle-fill (used in email header template).
    """
    if not event.customer_email:
        logger.warning("_handle_paid_email: empty customer_email — skipping")
        return
    if not event.order:
        logger.warning("_handle_paid_email: empty order dict — skipping")
        return
    send_order_confirmation(event.customer_email, event.order)


def _handle_paid_push(event: OrderPaidEvent) -> None:
    """
    Push customer after payment succeeds.
    Remix icon: ri-checkbox-circle-fill
    """
    from app.supabase_client import get_admin_supabase
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")
    oid   = _safe_oid(order)

    _push_user(
        get_admin_supabase(),
        uid,
        title=_Copy.PAID_PUSH_TITLE,
        body=_Copy.PAID_PUSH_BODY.format(oid=oid),
        icon=_Icon.PAID,
    )


def _handle_failed_push(event: OrderFailedEvent) -> None:
    """
    Push customer when payment fails or is cancelled.

    Dynamic reason routing:
      "payment_canceled" → cancellation copy + ri-forbid-2-fill icon
      "payment_failed"   → generic failure copy + ri-close-circle-fill
      <stripe error str> → verbatim Stripe message in body + ri-close-circle-fill
                           so customer sees the exact reason (e.g. 3DS failure,
                           insufficient funds, card declined).

    Remix icons: ri-close-circle-fill / ri-forbid-2-fill
    """
    from app.supabase_client import get_admin_supabase
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")

    if not uid:
        logger.warning("_handle_failed_push: no customer_id — skipping")
        return

    oid = _safe_oid(order)

    if event.reason == "payment_canceled":
        title = _Copy.CANCEL_PUSH_TITLE.format(oid=oid)
        body  = _Copy.CANCEL_PUSH_BODY
        icon  = _Icon.CANCELLED
    elif event.reason == "payment_failed":
        title = _Copy.FAILED_PUSH_TITLE.format(oid=oid)
        body  = _Copy.FAILED_PUSH_BODY
        icon  = _Icon.FAILED
    else:
        # Verbatim Stripe error — show it directly to the customer
        title = _Copy.FAILED_PUSH_TITLE.format(oid=oid)
        body  = event.reason
        icon  = _Icon.FAILED

    _push_user(get_admin_supabase(), uid, title=title, body=body, icon=icon)


def _handle_shipped_push(event: OrderShippedEvent) -> None:
    """
    Push customer when order ships.
    Remix icon: ri-truck-fill
    """
    from app.supabase_client import get_admin_supabase
    order = event.order or {}
    uid   = event.customer_id or order.get("customer_id", "")
    oid   = _safe_oid(order)

    body = _Copy.SHIPPED_PUSH_BODY
    if event.tracking_number:
        body += _Copy.SHIPPED_TRACKING_SUF.format(tracking=event.tracking_number)

    _push_user(
        get_admin_supabase(),
        uid,
        title=_Copy.SHIPPED_PUSH_TITLE.format(oid=oid),
        body=body,
        icon=_Icon.SHIPPED,
    )


def _handle_status_push(event: OrderStatusChangedEvent) -> None:
    """
    Push customer for admin-driven status transitions: delivered, refunded.
    Does not handle paid / shipped / payment-cancelled (separate events).
    Remix icons: ri-mail-check-fill (delivered), ri-refund-2-fill (refunded)
    """
    # (title_template, body, icon)
    _CONFIG: dict[str, tuple[str, str, str]] = {
        "delivered": (_Copy.DELIVERED_TITLE, _Copy.DELIVERED_BODY, _Icon.DELIVERED),
        "refunded":  (_Copy.REFUNDED_TITLE,  _Copy.REFUNDED_BODY,  _Icon.REFUNDED),
    }

    cfg = _CONFIG.get(event.new_status)
    if cfg is None:
        return  # unhandled status — no push

    from app.supabase_client import get_admin_supabase
    order              = event.order or {}
    oid                = _safe_oid(order)
    title_tpl, body, icon = cfg

    _push_user(
        get_admin_supabase(),
        event.customer_id,
        title=title_tpl.format(oid=oid),
        body=body,
        icon=icon,
    )


def _handle_low_stock_push(event: LowStockEvent) -> None:
    """
    Push admins on low-stock alert.
    Remix icon: ri-alert-fill
    """
    from app.supabase_client import get_admin_supabase

    _push_admins(
        get_admin_supabase(),
        title=_Copy.LOW_STOCK_TITLE.format(name=event.product_name),
        body=_Copy.LOW_STOCK_BODY.format(stock=event.stock, threshold=event.threshold),
        icon=_Icon.LOW_STOCK,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

_registered: bool = False


def register_default_handlers() -> None:
    """
    Wire up all default notification handlers.

    IDEMPOTENT — a module-level flag prevents duplicate registration on
    hot-reload or multiple test suite runs. Without this guard, every handler
    would fire N times per event (N = number of register calls), causing
    duplicate emails and push notifications.

    Call once at app startup from lifespan().
    """
    global _registered
    if _registered:
        logger.debug("register_default_handlers: already registered — skipping")
        return

    bus = get_event_bus()

    # New order → admin push only (customer notified after payment)
    bus.subscribe(OrderCreatedEvent,       _handle_new_order_admin_push)

    # Payment paid → customer email + push
    bus.subscribe(OrderPaidEvent,          _handle_paid_email)
    bus.subscribe(OrderPaidEvent,          _handle_paid_push)

    # Payment failed / cancelled → customer push with exact Stripe error
    bus.subscribe(OrderFailedEvent,        _handle_failed_push)

    # Shipped → customer push
    bus.subscribe(OrderShippedEvent,       _handle_shipped_push)

    # Admin status changes (delivered, refunded) → customer push
    bus.subscribe(OrderStatusChangedEvent, _handle_status_push)

    # Low stock → admin push
    bus.subscribe(LowStockEvent,           _handle_low_stock_push)

    _registered = True
    logger.info(
        "Event handlers registered | "
        "OrderCreated→AdminPush | "
        "OrderPaid→CustomerEmail+Push | "
        "OrderFailed→CustomerPush(+StripeError) | "
        "OrderShipped→CustomerPush | "
        "OrderStatus→CustomerPush | "
        "LowStock→AdminPush"
    )
