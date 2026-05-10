"""
Event Bus — Observer Pattern + Smart Notification Routing
===========================================================
Notification Flow (Updated):
  Order Created  → Sirf Admin push 🔔 (customer ko abhi kuch nahi)
  Order Paid     → Customer email (confirmation) + Customer push ✅
  Order Failed   → Customer push ❌ (payment reject/cancel)
  Order Shipped  → Customer push 📦
  Status change  → Customer push
  Low stock      → Admin push ⚠️

FIXED: Added `(event.order or {})` safe fallbacks to prevent NoneType crashes.
FIXED: Moved variable extractions inside try-except blocks for full safety.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Event types ───────────────────────────────────────────────────────────────

@dataclass
class OrderCreatedEvent:
    """Admin ko batao — customer ko kuch nahi abhi."""
    order: dict[str, Any]
    customer_email: str
    customer_id: str = ""


@dataclass
class OrderPaidEvent:
    """Payment succeed hua — ab customer ko email + push bhejo."""
    order: dict[str, Any]
    customer_email: str
    customer_id: str = ""


@dataclass
class OrderFailedEvent:
    """Payment fail/cancel hua — customer ko push bhejo."""
    order: dict[str, Any]
    customer_email: str
    customer_id: str = ""
    reason: str = "payment_failed"


@dataclass
class OrderShippedEvent:
    order: dict[str, Any]
    customer_email: str
    customer_id: str = ""
    tracking_number: str | None = None


@dataclass
class OrderStatusChangedEvent:
    order: dict[str, Any]
    customer_id: str
    old_status: str
    new_status: str


@dataclass
class OrderCancelledEvent:
    order_id: str
    customer_id: str
    reason: str = ""


@dataclass
class LowStockEvent:
    product_id: str
    product_name: str
    stock: int
    threshold: int


# ── Event Bus ─────────────────────────────────────────────────────────────────

EventType = type
Handler   = Callable[[Any], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        for handler in self._handlers[type(event)]:
            try:
                handler(event)
            except Exception as e:
                logger.error("Handler %s failed for %s: %s",
                             handler.__name__, type(event).__name__, e)


_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLERS — 1 function = 1 notification
# ══════════════════════════════════════════════════════════════════════════════

# ── PUSH — Admin: naya order aaya ─────────────────────────────────────────────

def _push_new_order_admin(event: OrderCreatedEvent) -> None:
    """
    PUSH admins — order place hote hi, turant admin ko batao.
    Customer ko is stage pe kuch nahi jaata.
    """
    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import broadcast_push_to_admins
        sb = get_admin_supabase()

        safe_order = event.order or {}
        oid = str(safe_order.get("id", "UNKNOWN"))[:8].upper()
        amt = safe_order.get("total_amount", 0)

        broadcast_push_to_admins(
            sb,
            title="🛒 Naya Order Aaya!",
            body=f"Order #{oid} — ₹{amt}",
            url="/admin.html",
        )
    except Exception as e:
        logger.warning("Admin new-order push failed: %s", e)


# ── EMAIL + PUSH — Customer: payment successful ───────────────────────────────

def _email_order_confirmation(event: OrderPaidEvent) -> None:
    """
    EMAIL — payment succeed hone ke BAAD bhejo.
    Order create pe nahi, payment confirm pe bhejo.
    """
    try:
        if not event.order:
            logger.warning("Order data missing in OrderPaidEvent, skipping email.")
            return

        from app.utils.email import send_order_confirmation
        send_order_confirmation(event.customer_email, event.order)
    except Exception as e:
        logger.error("Email order confirmation failed: %s", e)


def _push_order_paid(event: OrderPaidEvent) -> None:
    """
    PUSH customer — payment hone ke baad turant batao ✅
    """
    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import send_push_to_user
        sb = get_admin_supabase()

        safe_order = event.order or {}
        oid = str(safe_order.get("id", "UNKNOWN"))[:8].upper()
        amt = safe_order.get("total_amount", 0)

        send_push_to_user(
            sb,
            user_id=event.customer_id or safe_order.get("customer_id", ""),
            title="✅ Payment Successful!",
            body=f"Order #{oid} confirm ho gaya — ₹{amt}. Hum prepare kar rahe hain.",
            url="/orders.html",
        )
    except Exception as e:
        logger.warning("Customer paid push failed: %s", e)


# ── PUSH — Customer: payment failed/rejected ──────────────────────────────────

def _push_order_failed(event: OrderFailedEvent) -> None:
    """
    PUSH customer — payment fail/reject hone pe batao ❌
    Stock bhi restore ho chuka hoga is point pe.
    """
    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import send_push_to_user
        sb = get_admin_supabase()

        safe_order = event.order or {}
        oid = str(safe_order.get("id", "UNKNOWN"))[:8].upper()

        reason_map = {
            "payment_failed":   "Payment fail ho gaya. Dobara try karein.",
            "payment_canceled": "Payment cancel ho gayi.",
        }
        body = reason_map.get(event.reason, "Payment process nahi ho saka.")

        send_push_to_user(
            sb,
            user_id=event.customer_id or safe_order.get("customer_id", ""),
            title=f"❌ Order #{oid} — Payment Failed",
            body=body,
            url="/orders.html",
        )
    except Exception as e:
        logger.warning("Customer failed push failed: %s", e)


# ── PUSH — Customer: order shipped ───────────────────────────────────────────

def _push_order_shipped(event: OrderShippedEvent) -> None:
    """PUSH customer — shipped notification."""
    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import send_push_to_user
        sb = get_admin_supabase()

        safe_order = event.order or {}
        oid = str(safe_order.get("id", "UNKNOWN"))[:8].upper()

        body = f"Order #{oid} ship ho gaya!"
        if event.tracking_number:
            body += f" Tracking: {event.tracking_number}"

        send_push_to_user(
            sb,
            user_id=event.customer_id or safe_order.get("customer_id", ""),
            title="📦 Aapka Order Ship Ho Gaya!",
            body=body,
            url="/orders.html",
        )
    except Exception as e:
        logger.warning("Customer shipped push failed: %s", e)


# ── PUSH — Customer: status changes ──────────────────────────────────────────

def _push_order_status(event: OrderStatusChangedEvent) -> None:
    """PUSH customer — all status updates (delivered, cancelled, refunded)."""
    icons = {
        "delivered": "📬",
        "cancelled": "❌",
        "refunded":  "💰",
    }
    msgs = {
        "delivered": "Aapka order deliver ho gaya!",
        "cancelled": "Aapka order cancel ho gaya.",
        "refunded":  "Refund initiate kar diya gaya hai.",
    }
    # "paid" yahan handle nahi — woh OrderPaidEvent se aata hai
    if event.new_status not in icons:
        return

    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import send_push_to_user
        sb = get_admin_supabase()

        safe_order = event.order or {}
        oid = str(safe_order.get("id", "UNKNOWN"))[:8].upper()

        send_push_to_user(
            sb,
            user_id=event.customer_id,
            title=f"{icons[event.new_status]} Order #{oid} — {event.new_status.capitalize()}",
            body=msgs[event.new_status],
            url="/orders.html",
        )
    except Exception as e:
        logger.warning("Status change push failed [%s]: %s", event.new_status, e)


# ── PUSH — Admin: low stock ───────────────────────────────────────────────────

def _push_low_stock(event: LowStockEvent) -> None:
    """PUSH admins — low stock alert."""
    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import broadcast_push_to_admins
        sb = get_admin_supabase()
        broadcast_push_to_admins(
            sb,
            title="⚠️ Low Stock",
            body=f"{event.product_name} — {event.stock} bachi hai (threshold: {event.threshold})",
            url="/admin.html",
        )
    except Exception as e:
        logger.warning("Low stock push failed: %s", e)


# ── Wire up all handlers ──────────────────────────────────────────────────────

def register_default_handlers() -> None:
    """Called once at startup (lifespan)."""
    bus = get_event_bus()

    # Order created: sirf admin ko push (customer ko KUCH NAHI abhi)
    bus.subscribe(OrderCreatedEvent, _push_new_order_admin)

    # Order paid: customer ko email + push dono
    bus.subscribe(OrderPaidEvent, _email_order_confirmation)
    bus.subscribe(OrderPaidEvent, _push_order_paid)

    # Order failed/rejected: customer ko push
    bus.subscribe(OrderFailedEvent, _push_order_failed)

    # Shipped: customer ko push
    bus.subscribe(OrderShippedEvent, _push_order_shipped)

    # Status changes (delivered, cancelled, refunded): customer push
    bus.subscribe(OrderStatusChangedEvent, _push_order_status)

    # Low stock: admin push
    bus.subscribe(LowStockEvent, _push_low_stock)

    logger.info(
        "Handlers registered | "
        "OrderCreated→AdminPush | "
        "OrderPaid→CustomerEmail+Push | "
        "OrderFailed→CustomerPush | "
        "Shipped→CustomerPush | "
        "Status→CustomerPush | "
        "LowStock→AdminPush"
    )