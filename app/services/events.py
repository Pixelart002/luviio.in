"""
Event Bus — Observer Pattern
==============================
Pattern: Observer / Event-Driven (Publish-Subscribe)
Why: Order creation triggers email + analytics + notifications.
     Direct calls = tight coupling, every new side-effect needs changing the router.

LLD concepts applied:
  Observer Pattern    → publisher knows nothing about subscribers
  Loose Coupling      → OrderService fires event; EmailService listens, unaware of order logic
  Open/Closed         → add new subscribers (SMS, analytics, webhooks) without touching order code
  Single Responsibility → each handler has one job
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
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


# ── Simple synchronous event bus ──────────────────────────────────────────────

EventType = type
Handler = Callable[[Any], None]


class EventBus:
    """
    In-process synchronous event bus.
    Upgrade path: swap for Celery/Redis queue for async — interface stays the same.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        """Fire all handlers for this event type. Failures are isolated — one bad handler
        never blocks others or breaks the main flow."""
        for handler in self._handlers[type(event)]:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    "Event handler %s failed for %s: %s",
                    handler.__name__, type(event).__name__, e,
                )


# ── Singleton bus instance ────────────────────────────────────────────────────

_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


# ── Email handlers (subscribers) ─────────────────────────────────────────────

def _handle_order_created(event: OrderCreatedEvent) -> None:
    from app.utils.email import send_order_confirmation
    send_order_confirmation(event.customer_email, event.order)


def _handle_order_shipped(event: OrderShippedEvent) -> None:
    from app.utils.email import send_order_shipped
    send_order_shipped(event.customer_email, event.order, event.tracking_number)


def register_default_handlers() -> None:
    """Wire up default subscribers. Called once at startup."""
    bus = get_event_bus()
    bus.subscribe(OrderCreatedEvent, _handle_order_created)
    bus.subscribe(OrderShippedEvent, _handle_order_shipped)
    # Add SMS, analytics, Slack alerts here without touching order router