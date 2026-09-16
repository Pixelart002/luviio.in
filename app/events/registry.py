"""
Events Registry
==============
Path: app/events/registry.py

Registers all background task handlers to their respective events on the EventBus.
"""
import asyncio
import logging

from app.events.bus import (
    LowStockEvent,
    OrderCreatedEvent,
    OrderFailedEvent,
    OrderPaidEvent,
    OrderShippedEvent,
    OrderStatusChangedEvent,
    get_event_bus,
)
from app.events.handlers.order_handlers import (
    handle_failed_push,
    handle_low_stock_push,
    handle_new_order_admin_push,
    handle_paid_email,
    handle_paid_push,
    handle_shipped_push,
    handle_status_push,
)
from app.events.handlers.settings_handlers import handle_setting_reset, handle_setting_updated
from app.events.settings_events import SettingResetEvent, SettingUpdatedEvent

logger = logging.getLogger(__name__)
_registered: bool = False


def _install_durable_publish_adapter(bus) -> None:
    """Route transaction-backed events to the DB outbox without duplicate dispatch."""
    if getattr(bus, "_durable_publish_adapter_installed", False):
        return

    legacy_publish = bus.publish

    async def _run_durable(event) -> None:
        try:
            if isinstance(event, OrderFailedEvent):
                # Some gateway failures have no persisted DB mutation to trigger from.
                legacy_publish(event)
                return
            await bus.publish_durable(event)
        except Exception:
            logger.exception("Durable event publish failed | type=%s", type(event).__name__)

    def durable_publish(event) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_run_durable(event))
            return
        if loop.is_running():
            loop.create_task(_run_durable(event))

    bus.publish = durable_publish
    bus._durable_publish_adapter_installed = True


def register_all_event_handlers() -> None:
    """Idempotent — safe for hot-reload and tests. Call once in main.py."""
    global _registered
    if _registered:
        logger.debug("Event handlers already registered | action=skip")
        return

    bus = get_event_bus()

    bus.subscribe(OrderCreatedEvent, handle_new_order_admin_push)
    bus.subscribe(OrderPaidEvent, handle_paid_email)
    bus.subscribe(OrderPaidEvent, handle_paid_push)
    bus.subscribe(OrderFailedEvent, handle_failed_push)
    bus.subscribe(OrderShippedEvent, handle_shipped_push)
    bus.subscribe(OrderStatusChangedEvent, handle_status_push)
    bus.subscribe(LowStockEvent, handle_low_stock_push)

    bus.subscribe(SettingUpdatedEvent, handle_setting_updated)
    bus.subscribe(SettingResetEvent, handle_setting_reset)

    _install_durable_publish_adapter(bus)
    _registered = True
    logger.info("Event handlers registered | durable_outbox=true")
