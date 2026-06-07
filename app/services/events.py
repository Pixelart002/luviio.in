"""
Event Bus — Observer Pattern + Background Processing
=====================================================
Path: app/services/events.py

Architecture Upgrades:
  1. Handlers completely removed from this file.
  2. This file ONLY contains the Event Bus Engine, Dead Letter Queue, and Event Definitions.
  3. Safe Dataclass serialization and Graceful shutdown maintained.
"""
from __future__ import annotations

import atexit
import dataclasses
import logging
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "EventBus", "get_event_bus", 
    "OrderCreatedEvent", "OrderPaidEvent", "OrderFailedEvent",
    "OrderShippedEvent", "OrderStatusChangedEvent", "LowStockEvent",
]

# ── Configuration ─────────────────────────────────────────────────────────────
_HANDLER_POOL_SIZE = 4
_HANDLER_TIMEOUT_SECONDS = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2
_MAX_DEAD_LETTERS = 1000

_handler_pool = ThreadPoolExecutor(max_workers=_HANDLER_POOL_SIZE, thread_name_prefix="event-handler")

# ══════════════════════════════════════════════════════════════════════════════
#  EVENT DATACLASSES
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
#  DEAD LETTER QUEUE & METRICS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DeadLetter:
    event_id: str
    event_type: str
    event_data: dict[str, Any]
    error: str
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0

class DeadLetterQueue:
    def __init__(self, max_size: int = _MAX_DEAD_LETTERS):
        self._queue: list[DeadLetter] = []
        self._max_size = max_size
        self._lock = threading.Lock()
    
    def push(self, dead_letter: DeadLetter) -> None:
        with self._lock:
            if len(self._queue) >= self._max_size: self._queue.pop(0)
            self._queue.append(dead_letter)
    
    def get_all(self) -> list[DeadLetter]:
        with self._lock: return list(self._queue)
    
    def clear(self) -> None:
        with self._lock: self._queue.clear()
    
    def size(self) -> int:
        with self._lock: return len(self._queue)

class EventMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.published: dict[str, int] = defaultdict(int)
        self.succeeded: dict[str, int] = defaultdict(int)
        self.failed: dict[str, int] = defaultdict(int)
        self.retried: dict[str, int] = defaultdict(int)
        self.dead_lettered: dict[str, int] = defaultdict(int)
    
    def record_publish(self, event_type: str) -> None:
        with self._lock: self.published[event_type] += 1
    def record_success(self, event_type: str) -> None:
        with self._lock: self.succeeded[event_type] += 1
    def record_failure(self, event_type: str) -> None:
        with self._lock: self.failed[event_type] += 1
    def record_retry(self, event_type: str) -> None:
        with self._lock: self.retried[event_type] += 1
    def record_dead_letter(self, event_type: str) -> None:
        with self._lock: self.dead_lettered[event_type] += 1
    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "published": dict(self.published), "succeeded": dict(self.succeeded),
                "failed": dict(self.failed), "retried": dict(self.retried),
                "dead_lettered": dict(self.dead_lettered), "dead_letter_queue_size": dead_letter_queue.size(),
            }

dead_letter_queue = DeadLetterQueue()
event_metrics = EventMetrics()

# ══════════════════════════════════════════════════════════════════════════════
#  EVENT BUS
# ══════════════════════════════════════════════════════════════════════════════

EventType = type
Handler   = Callable[[Any], None]

class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)
        logger.debug("Handler subscribed | event=%s handler=%s", event_type.__name__, handler.__name__)

    def publish(self, event: Any) -> None:
        event_type, event_id = type(event), str(uuid.uuid4())[:8]
        handlers = self._handlers.get(event_type, [])
        if not handlers: return
        
        event_metrics.record_publish(event_type.__name__)
        logger.info("Event published | id=%s type=%s handlers=%d", event_id, event_type.__name__, len(handlers))
        
        for handler in handlers:
            _handler_pool.submit(_run_handler_with_retry, handler, event, event_id, event_type.__name__)

    def get_stats(self) -> dict[str, Any]: return event_metrics.get_stats()
    def get_dead_letters(self) -> list[DeadLetter]: return dead_letter_queue.get_all()

    def replay_dead_letters(self) -> int:
        letters = dead_letter_queue.get_all()
        dead_letter_queue.clear()
        count = 0
        for letter in letters:
            for event_type, handlers in self._handlers.items():
                if event_type.__name__ == letter.event_type:
                    for handler in handlers:
                        _handler_pool.submit(_run_handler_with_retry, handler, letter.event_data, letter.event_id, letter.event_type)
                    count += 1
                    break
        logger.info("Dead letters replayed | count=%d", count)
        return count
        
    def shutdown(self, wait: bool = True) -> None:
        logger.info("Shutting down event handler thread pool...")
        _handler_pool.shutdown(wait=wait, cancel_futures=False)

def _run_handler_with_retry(handler: Handler, event: Any, event_id: str, event_type_name: str) -> None:
    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            future = _handler_pool.submit(_run_handler, handler, event)
            future.result(timeout=_HANDLER_TIMEOUT_SECONDS)
            event_metrics.record_success(event_type_name)
            if attempt > 1: event_metrics.record_retry(event_type_name)
            return
        except FutureTimeoutError:
            last_error = f"Timeout after {_HANDLER_TIMEOUT_SECONDS}s"
            logger.warning("Handler timeout | id=%s handler=%s attempt=%d/%d", event_id, handler.__name__, attempt, _MAX_RETRIES)
        except Exception as exc:
            last_error = str(exc)[:500]
            logger.warning("Handler failed | id=%s handler=%s attempt=%d/%d error=%s", event_id, handler.__name__, attempt, _MAX_RETRIES, last_error)
        if attempt < _MAX_RETRIES: time.sleep(_RETRY_BACKOFF_BASE ** attempt)
    
    event_metrics.record_failure(event_type_name)
    event_metrics.record_dead_letter(event_type_name)
    
    try: event_dict = dataclasses.asdict(event) if dataclasses.is_dataclass(event) else {"event": str(event)}
    except Exception: event_dict = {"event": str(event)}
        
    dead_letter_queue.push(DeadLetter(event_id=event_id, event_type=event_type_name, event_data=event_dict, error=last_error or "Unknown error", retry_count=_MAX_RETRIES))
    logger.error("Handler permanently failed — moved to dead letter queue | id=%s handler=%s", event_id, handler.__name__)

def _run_handler(handler: Handler, event: Any) -> None:
    try: handler(event)
    except Exception as exc:
        logger.error("Handler %s raised for %s: %s", handler.__name__, type(event).__name__, exc)
        raise

_bus = EventBus()
def get_event_bus() -> EventBus: return _bus

def _shutdown_thread_pool():
    logger.info("Atexit: Shutting down event handler thread pool...")
    _handler_pool.shutdown(wait=True, cancel_futures=False)

atexit.register(_shutdown_thread_pool)