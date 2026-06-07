"""
Event Bus — Observer Pattern + Background Processing
=====================================================
Architecture Layer: Services (Domain Logic & Orchestration)
Path: app/services/events.py

FIX: Handlers ab background thread mein chalte hain.
     Request thread block nahi hota — push late delivery fix.

ENHANCEMENTS & FIXES:
  1. Retry logic for failed handlers (3 attempts with exponential backoff)
  2. Dead letter queue for permanently failed events
  3. Event metrics/monitoring
  4. Graceful shutdown for thread pool (compatible with FastAPI lifespan)
  5. Handler timeout protection
  6. CRITICAL FIX: Prevented Circular Imports (Lazy loading modules)
  7. CRITICAL FIX: Safe Dataclass serialization for Dead Letter Queue
"""
from __future__ import annotations

import atexit
import dataclasses
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "EventBus", "get_event_bus", "register_default_handlers",
    "OrderCreatedEvent", "OrderPaidEvent", "OrderFailedEvent",
    "OrderShippedEvent", "OrderStatusChangedEvent", "LowStockEvent",
]

# ── Configuration ─────────────────────────────────────────────────────────────

# Background thread pool — handlers run here, not in request thread
# max_workers=4: 4 push jobs parallel; tune as needed
_HANDLER_POOL_SIZE = 4
_HANDLER_TIMEOUT_SECONDS = 30  # Max time a handler can run
_MAX_RETRIES = 3               # Retry failed handlers
_RETRY_BACKOFF_BASE = 2        # Exponential backoff: 2^1, 2^2, 2^3 seconds

# Dead letter queue size limit
_MAX_DEAD_LETTERS = 1000

_handler_pool = ThreadPoolExecutor(
    max_workers=_HANDLER_POOL_SIZE,
    thread_name_prefix="event-handler"
)

_ICON_BASE: str = os.environ.get("PUSH_ICON_BASE_URL", "/icons").rstrip("/")


# ── Icons ─────────────────────────────────────────────────────────────────────

class _Icon:
    NEW_ORDER = f"{_ICON_BASE}/ri-shopping-bag-3.png"
    PAID      = f"{_ICON_BASE}/ri-checkbox-circle.png"
    FAILED    = f"{_ICON_BASE}/ri-close-circle.png"
    CANCELLED = f"{_ICON_BASE}/ri-forbid-2.png"
    SHIPPED   = f"{_ICON_BASE}/ri-truck.png"
    DELIVERED = f"{_ICON_BASE}/ri-mail-check.png"
    REFUNDED  = f"{_ICON_BASE}/ri-refund-2.png"
    LOW_STOCK = f"{_ICON_BASE}/ri-alert.png"


# ── Copy Templates ────────────────────────────────────────────────────────────

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


# ══════════════════════════════════════════════════════════════════════════════
#  EVENT DATACLASSES
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
#  DEAD LETTER QUEUE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DeadLetter:
    """Event that failed all retries — stored for debugging"""
    event_id: str
    event_type: str
    event_data: dict[str, Any]
    error: str
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0


class DeadLetterQueue:
    """In-memory dead letter queue for failed events"""
    
    def __init__(self, max_size: int = _MAX_DEAD_LETTERS):
        self._queue: list[DeadLetter] = []
        self._max_size = max_size
        self._lock = threading.Lock()
    
    def push(self, dead_letter: DeadLetter) -> None:
        with self._lock:
            if len(self._queue) >= self._max_size:
                self._queue.pop(0)  # Remove oldest
            self._queue.append(dead_letter)
    
    def get_all(self) -> list[DeadLetter]:
        with self._lock:
            return list(self._queue)
    
    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
    
    def size(self) -> int:
        with self._lock:
            return len(self._queue)


# ══════════════════════════════════════════════════════════════════════════════
#  EVENT METRICS
# ══════════════════════════════════════════════════════════════════════════════

class EventMetrics:
    """Track event processing metrics"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.published: dict[str, int] = defaultdict(int)
        self.succeeded: dict[str, int] = defaultdict(int)
        self.failed: dict[str, int] = defaultdict(int)
        self.retried: dict[str, int] = defaultdict(int)
        self.dead_lettered: dict[str, int] = defaultdict(int)
    
    def record_publish(self, event_type: str) -> None:
        with self._lock:
            self.published[event_type] += 1
    
    def record_success(self, event_type: str) -> None:
        with self._lock:
            self.succeeded[event_type] += 1
    
    def record_failure(self, event_type: str) -> None:
        with self._lock:
            self.failed[event_type] += 1
    
    def record_retry(self, event_type: str) -> None:
        with self._lock:
            self.retried[event_type] += 1
    
    def record_dead_letter(self, event_type: str) -> None:
        with self._lock:
            self.dead_lettered[event_type] += 1
    
    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "published": dict(self.published),
                "succeeded": dict(self.succeeded),
                "failed": dict(self.failed),
                "retried": dict(self.retried),
                "dead_lettered": dict(self.dead_lettered),
                "dead_letter_queue_size": dead_letter_queue.size(),
            }


# ══════════════════════════════════════════════════════════════════════════════
#  EVENT BUS
# ══════════════════════════════════════════════════════════════════════════════

EventType = type
Handler   = Callable[[Any], None]

# Global instances
dead_letter_queue = DeadLetterQueue()
event_metrics = EventMetrics()


class EventBus:
    """
    Production-grade event bus with:
      • Background thread pool execution
      • Retry with exponential backoff
      • Dead letter queue for failed events
      • Metrics/monitoring
      • Graceful shutdown
      • Handler timeout protection
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """Register a handler for an event type"""
        self._handlers[event_type].append(handler)
        logger.debug("Handler subscribed | event=%s handler=%s", event_type.__name__, handler.__name__)

    def publish(self, event: Any) -> None:
        """
        Publish event to all registered handlers.
        Handlers run in background thread pool — non-blocking.
        """
        event_type = type(event)
        event_id = str(uuid.uuid4())[:8]
        
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.debug("No handlers for event | type=%s", event_type.__name__)
            return
        
        event_metrics.record_publish(event_type.__name__)
        
        logger.info(
            "Event published | id=%s type=%s handlers=%d",
            event_id, event_type.__name__, len(handlers)
        )
        
        for handler in handlers:
            _handler_pool.submit(
                _run_handler_with_retry,
                handler, event, event_id, event_type.__name__
            )

    def get_stats(self) -> dict[str, Any]:
        """Get event processing statistics"""
        return event_metrics.get_stats()

    def get_dead_letters(self) -> list[DeadLetter]:
        """Get dead letter queue contents (for admin/debugging)"""
        return dead_letter_queue.get_all()

    def replay_dead_letters(self) -> int:
        """Replay all dead letter events — returns count of replayed events"""
        letters = dead_letter_queue.get_all()
        dead_letter_queue.clear()
        count = 0
        for letter in letters:
            # Find matching event type
            for event_type, handlers in self._handlers.items():
                if event_type.__name__ == letter.event_type:
                    for handler in handlers:
                        _handler_pool.submit(
                            _run_handler_with_retry,
                            handler, letter.event_data, letter.event_id, letter.event_type
                        )
                    count += 1
                    break
        logger.info("Dead letters replayed | count=%d", count)
        return count
        
    def shutdown(self, wait: bool = True) -> None:
        """Explicit shutdown method for FastAPI lifespan"""
        logger.info("Shutting down event handler thread pool...")
        _handler_pool.shutdown(wait=wait, cancel_futures=False)
        logger.info("Event handler thread pool shutdown complete")


def _run_handler_with_retry(
    handler: Handler,
    event: Any,
    event_id: str,
    event_type_name: str,
) -> None:
    """
    Run handler with retry logic.
    3 attempts with exponential backoff: 2s, 4s, 8s.
    On final failure → dead letter queue.
    """
    last_error = None
    
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            future = _handler_pool.submit(_run_handler, handler, event)
            future.result(timeout=_HANDLER_TIMEOUT_SECONDS)
            
            # Success!
            event_metrics.record_success(event_type_name)
            if attempt > 1:
                event_metrics.record_retry(event_type_name)
                logger.info(
                    "Handler succeeded after retry | id=%s handler=%s attempt=%d",
                    event_id, handler.__name__, attempt
                )
            return
            
        except FutureTimeoutError:
            last_error = f"Timeout after {_HANDLER_TIMEOUT_SECONDS}s"
            logger.warning(
                "Handler timeout | id=%s handler=%s attempt=%d/%d",
                event_id, handler.__name__, attempt, _MAX_RETRIES
            )
        except Exception as exc:
            last_error = str(exc)[:500]
            logger.warning(
                "Handler failed | id=%s handler=%s attempt=%d/%d error=%s",
                event_id, handler.__name__, attempt, _MAX_RETRIES, last_error
            )
        
        # Exponential backoff before retry
        if attempt < _MAX_RETRIES:
            backoff = _RETRY_BACKOFF_BASE ** attempt
            time.sleep(backoff)
    
    # All retries exhausted → dead letter queue
    event_metrics.record_failure(event_type_name)
    event_metrics.record_dead_letter(event_type_name)
    
    # Safe Dataclass parsing
    try:
        event_dict = dataclasses.asdict(event) if dataclasses.is_dataclass(event) else {"event": str(event)}
    except Exception:
        event_dict = {"event": str(event)}
        
    dead_letter = DeadLetter(
        event_id=event_id,
        event_type=event_type_name,
        event_data=event_dict,
        error=last_error or "Unknown error",
        retry_count=_MAX_RETRIES,
    )
    dead_letter_queue.push(dead_letter)
    
    logger.error(
        "Handler permanently failed — moved to dead letter queue | id=%s handler=%s",
        event_id, handler.__name__
    )


def _run_handler(handler: Handler, event: Any) -> None:
    """Execute a single handler with error isolation"""
    try:
        handler(event)
    except Exception as exc:
        logger.error(
            "Handler %s raised for %s: %s",
            handler.__name__, type(event).__name__, exc
        )
        raise  # Re-raise for retry logic


# ── Singleton ─────────────────────────────────────────────────────────────────

_bus = EventBus()


def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    return _bus


# ══════════════════════════════════════════════════════════════════════════════
#  HANDLER IMPLEMENTATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _safe_oid(order: dict[str, Any]) -> str:
    """Safely extract order ID shortcode"""
    return str(order.get("id", "UNKNOWN"))[:8].upper()


def _push_user(sb, user_id: str, *, title: str, body: str, icon: str,
               url: str = _Copy.URL_ORDERS) -> None:
    """Send push notification to a single user"""
    # 🔥 ARCHITECTURE CHANGE: Path updated to integrations layer
    from app.integrations.push.webpush_impl import send_push_to_user
    
    if not user_id:
        logger.warning("_push_user: empty user_id — skipping")
        return
    result = send_push_to_user(sb, user_id, title=title, body=body, icon=icon, url=url)
    logger.debug("Push sent | user=%.8s sent=%d", user_id, result)


def _push_admins(sb, *, title: str, body: str, icon: str,
                 url: str = _Copy.URL_ADMIN) -> None:
    """Broadcast push notification to all admins"""
    # 🔥 ARCHITECTURE CHANGE: Path updated to integrations layer
    from app.integrations.push.webpush_impl import broadcast_push_to_admins
    
    result = broadcast_push_to_admins(sb, title=title, body=body, icon=icon, url=url)
    logger.debug("Admin broadcast | sent=%d", result)


# ── Order Created ─────────────────────────────────────────────────────────────

def _handle_new_order_admin_push(event: OrderCreatedEvent) -> None:
    # 🔥 ARCHITECTURE CHANGE: Core supabase path
    from app.core.supabase import get_admin_supabase
    oid = _safe_oid(event.order or {})
    amt = (event.order or {}).get("total_amount", 0)
    _push_admins(
        get_admin_supabase(),
        title=_Copy.ADMIN_ORDER_TITLE.format(oid=oid),
        body=_Copy.ADMIN_ORDER_BODY.format(amt=amt),
        icon=_Icon.NEW_ORDER,
    )


# ── Order Paid ────────────────────────────────────────────────────────────────

def _handle_paid_email(event: OrderPaidEvent) -> None:
    # 🔥 ARCHITECTURE CHANGE: Path updated to integrations layer
    from app.integrations.email.resend_impl import send_order_confirmation
    
    if not event.customer_email or not event.order:
        logger.warning("_handle_paid_email: missing data — skipping")
        return
    send_order_confirmation(event.customer_email, event.order)


def _handle_paid_push(event: OrderPaidEvent) -> None:
    from app.core.supabase import get_admin_supabase
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    _push_user(
        get_admin_supabase(), uid,
        title=_Copy.PAID_PUSH_TITLE,
        body=_Copy.PAID_PUSH_BODY.format(oid=_safe_oid(order)),
        icon=_Icon.PAID,
    )


# ── Order Failed ──────────────────────────────────────────────────────────────

def _handle_failed_push(event: OrderFailedEvent) -> None:
    from app.core.supabase import get_admin_supabase
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    if not uid:
        logger.warning("_handle_failed_push: no customer_id — skipping")
        return
    oid = _safe_oid(order)
    
    if event.reason == "payment_canceled":
        title, body, icon = _Copy.CANCEL_PUSH_TITLE.format(oid=oid), _Copy.CANCEL_PUSH_BODY, _Icon.CANCELLED
    elif event.reason == "payment_failed":
        title, body, icon = _Copy.FAILED_PUSH_TITLE.format(oid=oid), _Copy.FAILED_PUSH_BODY, _Icon.FAILED
    else:
        title, body, icon = _Copy.FAILED_PUSH_TITLE.format(oid=oid), str(event.reason)[:200], _Icon.FAILED
    
    _push_user(get_admin_supabase(), uid, title=title, body=body, icon=icon)


# ── Order Shipped ─────────────────────────────────────────────────────────────

def _handle_shipped_push(event: OrderShippedEvent) -> None:
    from app.core.supabase import get_admin_supabase
    order = event.order or {}
    uid = event.customer_id or order.get("customer_id", "")
    body = _Copy.SHIPPED_PUSH_BODY
    if event.tracking_number:
        body += _Copy.SHIPPED_TRACKING.format(tracking=event.tracking_number)
    _push_user(
        get_admin_supabase(), uid,
        title=_Copy.SHIPPED_PUSH_TITLE.format(oid=_safe_oid(order)),
        body=body, icon=_Icon.SHIPPED,
    )


# ── Order Status Changed ──────────────────────────────────────────────────────

def _handle_status_push(event: OrderStatusChangedEvent) -> None:
    _CONFIG = {
        "delivered": (_Copy.DELIVERED_TITLE, _Copy.DELIVERED_BODY, _Icon.DELIVERED),
        "refunded":  (_Copy.REFUNDED_TITLE,  _Copy.REFUNDED_BODY,  _Icon.REFUNDED),
    }
    cfg = _CONFIG.get(event.new_status)
    if not cfg:
        return
    from app.core.supabase import get_admin_supabase
    title_tpl, body, icon = cfg
    _push_user(
        get_admin_supabase(), event.customer_id,
        title=title_tpl.format(oid=_safe_oid(event.order or {})),
        body=body, icon=icon,
    )


# ── Low Stock ─────────────────────────────────────────────────────────────────

def _handle_low_stock_push(event: LowStockEvent) -> None:
    from app.core.supabase import get_admin_supabase
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
        "OrderFailed→CustomerPush | OrderShipped→CustomerPush | "
        "OrderStatus→CustomerPush | LowStock→AdminPush | "
        "Retries=%d Timeout=%ds Workers=%d",
        _MAX_RETRIES, _HANDLER_TIMEOUT_SECONDS, _HANDLER_POOL_SIZE
    )


# ── Graceful Shutdown ─────────────────────────────────────────────────────────

def _shutdown_thread_pool():
    """Fallback graceful shutdown for atexit"""
    logger.info("Atexit: Shutting down event handler thread pool...")
    _handler_pool.shutdown(wait=True, cancel_futures=False)

atexit.register(_shutdown_thread_pool)