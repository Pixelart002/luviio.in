"""Application event bus with durable outbox-backed dispatch and retry support."""
from __future__ import annotations

import asyncio
import atexit
import dataclasses
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from app.events.outbox import (
    claim_event,
    enqueue_event,
    fetch_pending,
    mark_completed,
    mark_retry,
    recover_stale_processing,
)
from app.events.settings_events import SettingResetEvent, SettingUpdatedEvent

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
_OUTBOX_MAX_ATTEMPTS = 8

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
        value: Any = dataclasses.asdict(event)
    elif isinstance(event, dict):
        value = dict(event)
    else:
        value = {"event": str(event)}
    return json.loads(json.dumps(value, default=str))


def _event_class(event_type_name: str) -> type[Any] | None:
    return {
        cls.__name__: cls
        for cls in _EVENT_CLASSES
    }.get(event_type_name)


async def _invoke_handler(handler: Handler, event: Any) -> None:
    if asyncio.iscoroutinefunction(handler):
        await asyncio.wait_for(handler(event), timeout=_HANDLER_TIMEOUT_SECONDS)
        return
    await asyncio.wait_for(asyncio.to_thread(handler, event), timeout=_HANDLER_TIMEOUT_SECONDS)


async def _async_run_handler_with_retry(
    handler: Handler,
    event: Any,
    event_id: str,
    event_type_name: str,
) -> bool:
    last_error = "Unknown error"
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await _invoke_handler(handler, event)
            event_metrics.record_success(event_type_name)
            if attempt > 1:
                event_metrics.record_retry(event_type_name)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = str(exc)[:500]
            logger.warning(
                "Event handler failed | id=%s handler=%s attempt=%d/%d error=%s",
                event_id,
                getattr(handler, "__name__", repr(handler)),
                attempt,
                _MAX_RETRIES,
                last_error,
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_BACKOFF_BASE ** attempt)

    _dead_letter(event_id, event_type_name, event, last_error)
    return False


def _run_async_handler_from_worker(
    handler: Handler,
    event: Any,
    event_id: str,
    event_type_name: str,
) -> None:
    try:
        asyncio.run(_async_run_handler_with_retry(handler, event, event_id, event_type_name))
    except Exception as exc:
        logger.exception(
            "Async event worker crashed | id=%s handler=%s error=%s",
            event_id,
            getattr(handler, "__name__", repr(handler)),
            exc,
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
                event_id,
                getattr(handler, "__name__", repr(handler)),
                attempt,
                _MAX_RETRIES,
                last_error,
            )
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF_BASE ** attempt)
    _dead_letter(event_id, event_type_name, event, last_error)


def _dead_letter(event_id: str, event_type_name: str, event: Any, error: str) -> None:
    event_metrics.record_failure(event_type_name)
    event_metrics.record_dead_letter(event_type_name)
    dead_letter_queue.push(
        DeadLetter(
            event_id=event_id,
            event_type=event_type_name,
            event_data=_serialize_event(event),
            error=error,
            retry_count=_MAX_RETRIES,
        )
    )
    logger.error(
        "Event handler permanently failed; moved to in-memory DLQ | id=%s type=%s",
        event_id,
        event_type_name,
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
            event_type.__name__,
            getattr(handler, "__name__", repr(handler)),
        )

    async def publish_durable(self, event: Any) -> str:
        """Persist an event before dispatch; failed delivery remains retryable in DB."""
        event_type = type(event)
        event_id = str(uuid.uuid4())
        event_type_name = event_type.__name__
        payload = _serialize_event(event)
        event_metrics.record_publish(event_type_name)

        await enqueue_event(
            event_id=event_id,
            event_type=event_type_name,
            payload=payload,
        )
        await claim_event(event_id, 1)
        success = await self._dispatch_event(
            event_id=event_id,
            event_type_name=event_type_name,
            event=event,
        )
        if success:
            await mark_completed(event_id)
        else:
            await mark_retry(
                event_id,
                attempt=1,
                error="One or more event handlers failed",
                max_attempts=_OUTBOX_MAX_ATTEMPTS,
            )
        return event_id

    async def _dispatch_event(
        self,
        *,
        event_id: str,
        event_type_name: str,
        event: Any,
    ) -> bool:
        with self._lock:
            event_cls = type(event)
            handlers = tuple(self._handlers.get(event_cls, ()))
        if not handlers:
            logger.debug(
                "Event has no registered handlers | id=%s type=%s",
                event_id,
                event_type_name,
            )
            return True

        results = await asyncio.gather(
            *[
                _async_run_handler_with_retry(
                    handler,
                    event,
                    event_id,
                    event_type_name,
                )
                for handler in handlers
            ],
            return_exceptions=True,
        )
        return all(result is True for result in results)

    async def dispatch_outbox(self, limit: int = 50) -> int:
        """Recover stale claims and deliver pending outbox events."""
        await recover_stale_processing()
        rows = await fetch_pending(limit)
        processed = 0

        for row in rows:
            event_id = str(row.get("id"))
            event_type_name = str(row.get("event_type"))
            attempt = int(row.get("attempts") or 0) + 1
            if not await claim_event(event_id, attempt):
                continue

            event_cls = _event_class(event_type_name)
            if event_cls is None:
                await mark_retry(
                    event_id,
                    attempt=attempt,
                    error=f"Unknown event type: {event_type_name}",
                    max_attempts=_OUTBOX_MAX_ATTEMPTS,
                )
                continue

            try:
                event = event_cls(**(row.get("payload") or {}))
                success = await self._dispatch_event(
                    event_id=event_id,
                    event_type_name=event_type_name,
                    event=event,
                )
                if success:
                    await mark_completed(event_id)
                    processed += 1
                else:
                    await mark_retry(
                        event_id,
                        attempt=attempt,
                        error="One or more event handlers failed",
                        max_attempts=_OUTBOX_MAX_ATTEMPTS,
                    )
            except Exception as exc:
                logger.exception(
                    "Durable event replay failed | id=%s type=%s",
                    event_id,
                    event_type_name,
                )
                await mark_retry(
                    event_id,
                    attempt=attempt,
                    error=str(exc),
                    max_attempts=_OUTBOX_MAX_ATTEMPTS,
                )
        return processed

    def publish(self, event: Any) -> None:
        """Backward-compatible volatile publisher for tests/non-critical local use."""
        event_type = type(event)
        event_id = str(uuid.uuid4())
        with self._lock:
            handlers = tuple(self._handlers.get(event_type, ()))
        if not handlers:
            logger.debug("Event published without handlers | type=%s", event_type.__name__)
            return
        event_type_name = event_type.__name__
        event_metrics.record_publish(event_type_name)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                if loop is not None and loop.is_running():
                    loop.create_task(
                        _async_run_handler_with_retry(
                            handler,
                            event,
                            event_id,
                            event_type_name,
                        )
                    )
                else:
                    _handler_pool.submit(
                        _run_async_handler_from_worker,
                        handler,
                        event,
                        event_id,
                        event_type_name,
                    )
            else:
                _handler_pool.submit(
                    _run_handler_with_retry,
                    handler,
                    event,
                    event_id,
                    event_type_name,
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
                    dataclasses.replace(
                        letter,
                        error=f"Replay reconstruction failed: {exc}",
                    )
                )
                continue
            self.publish(event)
            replayed += 1
        dead_letter_queue.clear()
        for letter in retained:
            dead_letter_queue.push(letter)
        logger.info(
            "Dead letters replayed | count=%d retained=%d",
            replayed,
            len(retained),
        )
        return replayed

    def shutdown(self, wait: bool = True) -> None:
        _handler_pool.shutdown(wait=wait, cancel_futures=False)


_EVENT_CLASSES = (
    OrderCreatedEvent,
    OrderPaidEvent,
    OrderFailedEvent,
    OrderShippedEvent,
    OrderStatusChangedEvent,
    LowStockEvent,
    SettingUpdatedEvent,
    SettingResetEvent,
)

_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus


def _shutdown_thread_pool() -> None:
    logger.info("Atexit: shutting down event handler thread pool")
    _handler_pool.shutdown(wait=True, cancel_futures=False)


atexit.register(_shutdown_thread_pool)
