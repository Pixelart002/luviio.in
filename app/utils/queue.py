"""
Email Batch Queue
==================
Problem: Resend free tier = 3000 emails/month = ~100/day.
Solution: Queue emails, deduplicate, batch flush every 30s or when 10 queued.

Rules:
  - Welcome email     → immediate (1 per user, lifetime)
  - Order confirm     → immediate (critical, user expects it now)
  - Shipped           → immediate (user tracking info)
  - Everything else   → PUSH first, no email

This queue is for future bulk/marketing emails — keeps critical path fast.
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Any

logger = logging.getLogger(__name__)

BATCH_SIZE     = 10          # flush after N emails queued
FLUSH_INTERVAL = 30          # flush every N seconds
DEDUP_WINDOW   = 300         # ignore duplicate (same to+subject) within 5 minutes


@dataclass
class QueuedEmail:
    to:      str
    subject: str
    html:    str
    send_fn: Callable
    queued_at: float = field(default_factory=time.time)


class EmailQueue:
    """
    Thread-safe in-memory email queue with dedup + batch flush.
    For production, swap _queue list with Redis list — interface stays the same.
    """

    def __init__(self) -> None:
        self._queue: list[QueuedEmail]          = []
        self._sent_dedup: dict[str, float]      = {}   # key → timestamp
        self._lock  = asyncio.Lock()
        self._task: asyncio.Task | None         = None

    def start(self) -> None:
        """Start background flush loop — call from lifespan."""
        try:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._flush_loop())
            logger.info("Email queue started | batch=%d interval=%ds", BATCH_SIZE, FLUSH_INTERVAL)
        except RuntimeError:
            logger.warning("No event loop — email queue running in sync mode")

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def enqueue(self, to: str, subject: str, html: str, send_fn: Callable) -> None:
        """Add email to queue. Deduplicates same to+subject within DEDUP_WINDOW."""
        dedup_key = f"{to}|{subject}"
        now = time.time()

        async with self._lock:
            last_sent = self._sent_dedup.get(dedup_key, 0)
            if now - last_sent < DEDUP_WINDOW:
                logger.debug("Email deduped | to=%s subject=%s", to, subject)
                return

            self._queue.append(QueuedEmail(to=to, subject=subject, html=html, send_fn=send_fn))
            self._sent_dedup[dedup_key] = now
            logger.debug("Email queued | to=%s | queue_size=%d", to, len(self._queue))

            if len(self._queue) >= BATCH_SIZE:
                await self._flush()

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            async with self._lock:
                if self._queue:
                    await self._flush()

    async def _flush(self) -> None:
        """Send all queued emails. Called with lock held."""
        batch = self._queue[:]
        self._queue.clear()
        logger.info("Flushing email queue | count=%d", len(batch))

        for item in batch:
            try:
                # Run sync send_fn in thread pool so we don't block event loop
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, item.send_fn)
                logger.info("✓ Queued email sent | to=%s", item.to)
            except Exception as e:
                logger.error("✗ Queued email failed | to=%s | %s", item.to, e)

    def flush_sync(self) -> None:
        """Sync flush for non-async contexts."""
        items = self._queue[:]
        self._queue.clear()
        for item in items:
            try:
                item.send_fn()
            except Exception as e:
                logger.error("Queued email failed | to=%s | %s", item.to, e)


# ── Singleton ─────────────────────────────────────────────────────────────────
_queue = EmailQueue()

def get_email_queue() -> EmailQueue:
    return _queue