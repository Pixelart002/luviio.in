"""
Events Registry
==============
Path: app/events/registry.py

Registers all background task handlers to their respective events on the EventBus.
"""
import logging
from app.services.events import (
    get_event_bus, 
    OrderCreatedEvent, OrderPaidEvent, OrderFailedEvent, 
    OrderShippedEvent, OrderStatusChangedEvent, LowStockEvent
)
# 🔥 FIX: Path updated from hooks to events
from app.events.handlers.order_handlers import (
    handle_new_order_admin_push, handle_paid_email, 
    handle_paid_push, handle_failed_push, 
    handle_shipped_push, handle_status_push, 
    handle_low_stock_push
)

logger = logging.getLogger(__name__)
_registered: bool = False

# 🔥 FIX: Function renamed to make sense with 'events'
def register_all_event_handlers() -> None:
    """Idempotent — safe for hot-reload and tests. Call once in main.py."""
    global _registered
    if _registered:
        logger.debug("Event handlers already registered — skipping")
        return

    bus = get_event_bus()
    
    # ── Wire Handlers to Events ──
    bus.subscribe(OrderCreatedEvent,       handle_new_order_admin_push)
    bus.subscribe(OrderPaidEvent,          handle_paid_email)
    bus.subscribe(OrderPaidEvent,          handle_paid_push)
    bus.subscribe(OrderFailedEvent,        handle_failed_push)
    bus.subscribe(OrderShippedEvent,       handle_shipped_push)
    bus.subscribe(OrderStatusChangedEvent, handle_status_push)
    bus.subscribe(LowStockEvent,           handle_low_stock_push)

    _registered = True
    logger.info("✅ All Application Event Handlers registered successfully.")