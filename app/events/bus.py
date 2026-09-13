"""Application event bus with safe async/sync handler execution and DLQ support."""
from __future__ import annotations

import asyncio
import atexit
import dataclasses
import logging
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "EventBus", "get_event_bus",
    "OrderCreatedEvent", "OrderPaidEvent", "OrderFailedEvent",
    "OrderShippedEvent", "OrderStatusChangedEvent", "LowStockEvent",
]

_HANDLER_POOL_SIZE = 4
_HANDLER_TIMEOUT_SECONDS = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2
_MAX_DEAD_LETTERS = 1000

_handler_pool = ThreadPoolExecutor(
    max_workers=_HANDLER_POOL_SIZE,
    thread_name_prefix="event-handler",
)


@dataclass
class OrderCreatedEvent:
    order: dict[str, Any]
    customer_email: str
    customer_id: str = ""


@dataclass
class OrderPaidEvent:
    order: dict[str, Any]
    customer_email: str
    customer_id: str = ""


@dataclass
class OrderFailedEvent:
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
class LowStockEvent:
    product_id: str
    product_name: str
    stock: int
    threshold: int


@dataclass
class DeadLetter:
    event_id: str
    event_type: str
    event_data: dict[str, Any]
    error: str
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0


class DeadLetterQueue:
    def __init__(self, max_size: int = _MAX_DEAD_LETTERS) -> None:
        self._queue: list[DeadLetter] = []
        self._max_size = max_size
        self._lock = threading.Lock()

    def push(self, dead_letter: DeadLetter) -> None:
        with self._lock:
            if len(self._queue) >= self._max_size:
                self._queue.pop(0)
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


class EventMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.published: dict[str, int] = defaultdict(int)
        self.succeeded: dict[str, int] = defaultdict(int)
        self.failed: dict[str, int] = defaultdict(int)
        self.retried: dict[str, int] = defaultdict(int)
        self.dead_lettered: dict[str, int] = defaultdict(int)

    def _record(self, bucket: dict[str, int], event_type: str) -> None:
        with self._lock:
            bucket[event_type] += 1

    def record_publish(self, event_type: str) -> None:
        self._record(self.published, event_type)

    def record_success(self, event_type: str) -> None:
        self._record(self.succeeded, event_type)

    def record_failure(self, event_type: str) -> None:
        self._record(self.failed, event_type)

    def record_retry(self, event_type: str) -> None:
        self._record(self.retried, event_type)

    def record_dead_letter(self, event_type: str) -> None:
        self._record(self.dead_lettered, event_type)

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


dead_letter_queue = DeadLetterQueue()
event_metrics = EventMetrics()

EventType = type
Handler = Callable[[Any], Any]


def _serialize_event(event: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(event):
        return dataclasses.asdict(event)
    if isinstance(event, dict):
        return dict(event)
    return {"event": str(event)}


async def _async_run_handler_with_retry(
    handler: Handler,
    event: Any,
    event_id: str,
    event_type_name: str,
) -> None:
    last_error = "Unknown error"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await asyncio.wait_for(handler(event), timeout=_HANDLER_TIMEOUT_SECONDS)
            event_metrics.record_success(event_type_name)
            if attempt > 1:
                event_metrics.record_retry(event_type_name)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = str(exc)[:500]
            logger.warning(
                "Event handler failed | id=%s handler=%s attempt=%d/%d error=%s",
                event_id, handler.__name__, attempt, _MAX_RETRIES, last_error,
            )
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_BACKOFF_BASE ** attempt)

    event_metrics.record_failure(event_type_name)
    event_metrics.record_dead_letter(event_type_name)
    dead_letter_queue.push(
        DeadLetter(
            event_id=event_id,
            event_type=event_type_name,
            event_data=_serialize_event(event),
            error=last_error,
            retry_count=_MAX_RETRIES,
        )
    )
    logger.error(
        "Event handler permanently failed; moved to DLQ | id=%s handler=%s",
        event_id, handler.__name__,
    )


def _run_handler_with_retry(
    handler: Handler,
    event: Any,
    event_id: str,
    event_type_name: str,
) -> None:
    last_error = "Unknown error"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            handler(event)
            event_metrics.record_success(event_type_name)
            if attempt > 1:
                event_metrics.record_retry(event_type_name)
            return
        except Exception as exc:
            last_error = str(exc)[:500]
            logger.warning(
                "Event handler failed | id=%s handler=%s attempt=%d/%d error=%s",
                event_id, handler.__name__, attempt, _MAX_RETRIES, last_error,
            )
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF_BASE ** attempt)

    event_metrics.record_failure(event_type_name)
    event_metrics.record_dead_letter(event_type_name)
    dead_letter_queue.push(
        DeadLetter(
            event_id=event_id,
            event_type=event_type_name,
            event_data=_serialize_event(event),
            error=last_error,
            retry_count=_MAX_RETRIES,
        )
    )
    logger.error(
        "Event handler permanently failed; moved to DLQ | id=%s handler=%s",
        event_id, handler.__name__,
    )


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        with self._lock:
            if handler in self._handlers[event_type]:
                return
            self._handlers[event_type].append(handler)
        logger.debug(
            "Handler subscribed | event=%s handler=%s",
            event_type.__name__, handler.__name__,
        )

    def publish(self, event: Any) -> None:
        event_type = type(event)
        event_id = str(uuid.uuid4())
        with self._lock:
            handlers = tuple(self._handlers.get(event_type, ()))
        if not handlers:
            logger.debug("Event published without handlers | type=%s", event_type.__name__)
            return

        event_type_name = event_type.__name__
        event_metrics.record_publish(event_type_name)
        logger.info(
            "Event published | id=%s type=%s handlers=%d",
            event_id, event_type_name, len(handlers),
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        for handler in handlers:
            if asyncio.iscoroutinefunction(handler) and loop is not None and loop.is_running():
                loop.create_task(
                    _async_run_handler_with_retry(
                        handler, event, event_id, event_type_name,
                    )
                )
            elif asyncio.iscoroutinefunction(handler):
                # No active loop: run the async handler in a dedicated worker.
                _handler_pool.submit(_run_async_handler_from_worker, handler, event, event_id, event_type_name)
            else:
                # IMPORTANT: execute the sync retry wrapper directly in the pool.
                # Do not submit another future from inside a pool worker (deadlock risk).
                _handler_pool.submit(
                    _run_handler_with_retry,
                    handler, event, event_id, event_type_name,
                )

    def get_stats(self) -> dict[str, Any]:
        return event_metrics.get_stats()

    def get_dead_letters(self) -> list[DeadLetter]:
        return dead_letter_queue.get_all()

    def replay_dead_letters(self) -> int:
        letters = dead_letter_queue.get_all()
        if not letters:
            return 0

        event_types = {cls.__name__: cls for cls in _EVENT_CLASSES}
        replayed = 0
        retained: list[DeadLetter] = []

        for letter in letters:
            event_cls = event_types.get(letter.event_type)
            if event_cls is None:
                retained.append(letter)
                continue
            try:
                event = event_cls(**letter.event_data)
            except Exception as exc:
                retained.append(
                    dataclasses.replace(letter, error=f"Replay reconstruction failed: {exc}"),
                )
                continue
            self.publish(event)
            replayed += 1

        dead_letter_queue.clear()
        for letter in retained:
            dead_letter_queue.push(letter)
        logger.info("Dead letters replayed | count=%d retained=%d", replayed, len(retained))
        return replayed

    def shutdown(self, wait: bool = True) -> None:
        _handler_pool.shutdown(wait=wait, cancel_futures=False)


async def _run_async_handler_from_worker(
    handler: Handler,
    event: Any,
    event_id: str,
    event_type_name: str,
) -> None:
    await _async_run_handler_with_retry(handler, event, event_id, event_type_name)


_EVENT_CLASSES = (
    OrderCreatedEvent,
    OrderPaidEvent,
    OrderFailedEvent,
    OrderShippedEvent,
    OrderStatusChangedEvent,
    LowStockEvent,
)

_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


def _shutdown_thread_pool() -> None:
    logger.info("Atexit: shutting down event handler thread pool")
    _handler_pool.shutdown(wait=True, cancel_futures=False)


atexit.register(_shutdown_thread_pool)
