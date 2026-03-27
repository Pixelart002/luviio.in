"""
Event Bus — Observer Pattern + Smart Notification Routing
===========================================================
Strategy:
  EMAIL  → critical only: welcome + order confirmation
  PUSH   → everything real-time: shipped, status, admin alerts, low stock

Email budget saved:
  Before: 4 emails per order lifecycle
  After:  1 email per order (confirmation only)
  Everything else → Push (instant + free)
  
FIXED: Added `(event.order or {})` safe fallbacks to prevent NoneType attribute crashes.
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
    order: dict[str, Any]
    customer_email: str
    customer_id: str = ""


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

# ── EMAIL (critical only) ─────────────────────────────────────────────────────

def _email_order_confirmation(event: OrderCreatedEvent) -> None:
    """EMAIL — user expects this immediately after placing order."""
    try:
        # Safe check just in case order is missing
        if not event.order:
            logger.warning("Order data missing in OrderCreatedEvent, skipping email.")
            return
            
        from app.utils.email import send_order_confirmation
        send_order_confirmation(event.customer_email, event.order)
    except Exception as e:
        logger.error("Email order confirmation failed: %s", e)


# ── PUSH — admin alerts ───────────────────────────────────────────────────────

def _push_new_order_admin(event: OrderCreatedEvent) -> None:
    """PUSH admins — instant new order alert, zero email cost."""
    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import broadcast_push_to_admins
        sb  = get_admin_supabase()
        
        # SAFE EXTRACT: Use (event.order or {})
        safe_order = event.order or {}
        oid = str(safe_order.get("id", "UNKNOWN"))[:8].upper()
        amt = safe_order.get("total_amount", 0)
        
        broadcast_push_to_admins(
            sb,
            title="🛒 New Order Received",
            body=f"Order #{oid} — ₹{amt}",
            url="/admin.html",
        )
    except Exception as e:
        logger.warning("Admin new-order push failed: %s", e)


# ── PUSH — customer shipped ───────────────────────────────────────────────────

def _push_order_shipped(event: OrderShippedEvent) -> None:
    """PUSH customer — shipped notification replaces email entirely."""
    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import send_push_to_user
        sb  = get_admin_supabase()
        
        # SAFE EXTRACT
        safe_order = event.order or {}
        oid = str(safe_order.get("id", "UNKNOWN"))[:8].upper()
        
        body = f"Order #{oid} is on the way!"
        if event.tracking_number:
            body += f" Tracking: {event.tracking_number}"
            
        send_push_to_user(
            sb,
            user_id=event.customer_id or safe_order.get("customer_id", ""),
            title="📦 Your order has shipped!",
            body=body,
            url="/orders.html",
        )
    except Exception as e:
        logger.warning("Customer shipped push failed: %s", e)


# ── PUSH — order status changes ───────────────────────────────────────────────

def _push_order_status(event: OrderStatusChangedEvent) -> None:
    """PUSH customer — all status updates (paid, delivered, cancelled, refunded)."""
    icons = {
        "paid":      "✅",
        "delivered": "📬",
        "cancelled": "❌",
        "refunded":  "💰",
    }
    msgs = {
        "paid":      "Payment confirmed — we're preparing your order.",
        "delivered": "Your order has been delivered!",
        "cancelled": "Your order has been cancelled.",
        "refunded":  "Refund has been initiated.",
    }
    if event.new_status not in icons:
        return

    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import send_push_to_user
        sb = get_admin_supabase()
        
        # SAFE EXTRACT (Moved inside try block)
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


# ── PUSH — low stock admin alert ──────────────────────────────────────────────

def _push_low_stock(event: LowStockEvent) -> None:
    """PUSH admins — low stock alert. Zero emails for ops."""
    try:
        from app.supabase_client import get_admin_supabase
        from app.utils.push import broadcast_push_to_admins
        sb = get_admin_supabase()
        broadcast_push_to_admins(
            sb,
            title="⚠️ Low Stock",
            body=f"{event.product_name} — {event.stock} left (threshold: {event.threshold})",
            url="/admin.html",
        )
    except Exception as e:
        logger.warning("Low stock push failed: %s", e)


# ── Wire up all handlers ──────────────────────────────────────────────────────

def register_default_handlers() -> None:
    """Called once at startup (lifespan)."""
    bus = get_event_bus()

    # Order created: 1 email (critical) + 1 push to admin
    bus.subscribe(OrderCreatedEvent,       _email_order_confirmation)
    bus.subscribe(OrderCreatedEvent,       _push_new_order_admin)

    # Shipped: push only — no email
    bus.subscribe(OrderShippedEvent,       _push_order_shipped)

    # All status changes: push only
    bus.subscribe(OrderStatusChangedEvent, _push_order_status)

    # Low stock: push admins only
    bus.subscribe(LowStockEvent,           _push_low_stock)

    logger.info(
        "Handlers registered | "
        "EMAIL: order_confirm(1) | "
        "PUSH: admin_new_order, shipped, status_changes, low_stock"
    )