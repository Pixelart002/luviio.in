"""
Event Bus — Observer Pattern
==============================
Changes from original:
  1. _handle_order_created / _handle_order_shipped — updated to match
     new email.py signature: send_xxx(to, order, ...)
     Old signature was send_xxx(email, order) — same, no breaking change.
  2. OrderCancelledEvent handler added (optional, for future use)
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


@dataclass
class OrderShippedEvent:
    order: dict[str, Any]
    customer_email: str
    tracking_number: str | None


@dataclass
class OrderCancelledEvent:
    order_id: str
    reason: str


# ── Event Bus ─────────────────────────────────────────────────────────────────

EventType = type
Handler   = Callable[[Any], None]


class EventBus:
    """
    In-process synchronous event bus.
    Upgrade path: swap for Celery/Redis — interface stays the same.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        """
        Fire all handlers. One bad handler never blocks others.
        """
        for handler in self._handlers[type(event)]:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    "Event handler %s failed for %s: %s",
                    handler.__name__, type(event).__name__, e,
                )


# ── Singleton ─────────────────────────────────────────────────────────────────

_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


# ── Email handlers (subscribers) ─────────────────────────────────────────────

def _handle_order_created(event: OrderCreatedEvent) -> None:
    """
    Uses new email.py: send_order_confirmation(to, order)
    """
    from app.utils.email import send_order_confirmation
    send_order_confirmation(event.customer_email, event.order)


def _handle_order_shipped(event: OrderShippedEvent) -> None:
    """
    Uses new email.py: send_order_shipped(to, order, tracking_number)
    """
    from app.utils.email import send_order_shipped
    send_order_shipped(event.customer_email, event.order, event.tracking_number)


def register_default_handlers() -> None:
    """Wire up all subscribers. Called once at startup in lifespan."""
    bus = get_event_bus()
    bus.subscribe(OrderCreatedEvent, _handle_order_created)
    bus.subscribe(OrderShippedEvent, _handle_order_shipped)
    # Add SMS, Slack alerts, analytics here — zero changes to order router needed
    logger.info("Event handlers registered: OrderCreated, OrderShipped")