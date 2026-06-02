"""
Email Batch Queue — Production Grade
=====================================
Problem: Resend free tier = 3000 emails/month = ~100/day.
Solution: Queue emails, deduplicate, batch flush every 30s or when 10 queued.

Rules:
  - Welcome email     → immediate (1 per user, lifetime)
  - Order confirm     → immediate (critical, user expects it now)
  - Shipped           → immediate (user tracking info)
  - Cart reminder     → queued (non-critical, can batch)
  - Promo/Marketing   → queued (low priority)

ENHANCEMENTS:
  1. Priority queue — critical emails skip the queue
  2. Memory-safe dedup — automatic cleanup of old entries
  3. Graceful shutdown — flush remaining on app exit
  4. Metrics — queue depth, sent/failed/deduped counts
  5. Thread-safe — asyncio.Lock with safe initialization
  6. Sync fallback — works without event loop
  7. Configurable — batch size, flush interval, dedup window
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
BATCH_SIZE     = 10          # flush after N emails queued
FLUSH_INTERVAL = 30          # flush every N seconds
DEDUP_WINDOW   = 300         # ignore duplicate (same to+subject) within 5 minutes
MAX_QUEUE_SIZE = 100         # Max queue size before forcing flush
CLEANUP_INTERVAL = 600       # Cleanup old dedup entries every 10 minutes


# ══════════════════════════════════════════════════════════════════════════════
#  TYPES
# ══════════════════════════════════════════════════════════════════════════════

class EmailPriority(Enum):
    """Email priority — higher = sent first"""
    IMMEDIATE = 0   # Skip queue entirely
    HIGH = 1        # Order confirm, shipped
    NORMAL = 2      # Cart reminder
    LOW = 3         # Marketing, newsletters


@dataclass(order=True)
class QueuedEmail:
    """Email in queue — sortable by priority and queue time"""
    priority: EmailPriority = field(default=EmailPriority.NORMAL)
    queued_at: float = field(default_factory=time.time)
    to: str = field(default="")
    subject: str = field(default="")
    html: str = field(default="")
    send_fn: Callable = field(default=lambda: None)
    
    # Don't use these for sorting
    send_kwargs: dict = field(default_factory=dict, compare=False)


# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL QUEUE
# ══════════════════════════════════════════════════════════════════════════════

class EmailQueue:
    """
    Thread-safe in-memory email queue with:
      • Priority ordering (immediate > high > normal > low)
      • Deduplication (same to+subject within DEDUP_WINDOW)
      • Batch flushing (BATCH_SIZE or FLUSH_INTERVAL)
      • Memory cleanup (old dedup entries removed)
      • Graceful shutdown
    
    Production upgrade path: Replace _queue with Redis Sorted Set
    """

    def __init__(self) -> None:
        self._queue: list[QueuedEmail] = []
        self._sent_dedup: dict[str, float] = {}  # dedup_key → timestamp
        self._lock: asyncio.Lock | None = None
        self._flush_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        
        # Metrics
        self._metrics = {
            "queued": 0,
            "sent": 0,
            "failed": 0,
            "deduped": 0,
            "immediate": 0,
            "flushed_batches": 0,
        }
        self._started = False

    # ── Lock management ───────────────────────────────────────────────────────
    
    def _get_lock(self) -> asyncio.Lock:
        """Safely get or create the lock within the active event loop"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    
    def start(self) -> None:
        """Start background tasks — call from FastAPI lifespan"""
        if self._started:
            return
        
        try:
            loop = asyncio.get_running_loop()
            self._flush_task = loop.create_task(self._flush_loop())
            self._cleanup_task = loop.create_task(self._cleanup_loop())
            self._started = True
            logger.info(
                "Email queue started | batch=%d interval=%ds dedup=%ds",
                BATCH_SIZE, FLUSH_INTERVAL, DEDUP_WINDOW
            )
        except RuntimeError:
            logger.warning("No running event loop — email queue in sync-only mode")

    async def stop(self) -> None:
        """Graceful shutdown — flush remaining emails"""
        logger.info("Email queue stopping — flushing remaining emails...")
        
        if self._flush_task:
            self._flush_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # Flush remaining
        await self._flush()
        
        self._started = False
        logger.info(
            "Email queue stopped | stats: queued=%d sent=%d failed=%d deduped=%d immediate=%d",
            self._metrics["queued"], self._metrics["sent"],
            self._metrics["failed"], self._metrics["deduped"], self._metrics["immediate"]
        )

    # ── Core: Enqueue ─────────────────────────────────────────────────────────
    
    async def enqueue(
        self,
        to: str,
        subject: str,
        html: str,
        send_fn: Callable,
        *,
        priority: EmailPriority = EmailPriority.NORMAL,
        **send_kwargs,
    ) -> bool:
        """
        Add email to queue.
        
        Args:
            to: Recipient email
            subject: Email subject
            html: Email HTML body
            send_fn: Function that sends the email (e.g., resend.Emails.send)
            priority: EmailPriority — IMMEDIATE skips queue
            **send_kwargs: Extra args passed to send_fn
        
        Returns:
            True if queued, False if deduped
        """
        # ── IMMEDIATE: Skip queue, send now ────────────────────────────────────
        if priority == EmailPriority.IMMEDIATE:
            self._metrics["immediate"] += 1
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, send_fn, **send_kwargs)
                self._metrics["sent"] += 1
                logger.info("✓ Immediate email sent | to=%s subject=%s", to, subject)
                return True
            except RuntimeError:
                # No event loop — sync send
                try:
                    send_fn(**send_kwargs)
                    self._metrics["sent"] += 1
                    return True
                except Exception as exc:
                    self._metrics["failed"] += 1
                    logger.error("✗ Immediate email failed | to=%s: %s", to, exc)
                    return False
        
        # ── Dedup check ───────────────────────────────────────────────────────
        dedup_key = f"{to}|{subject}"
        now = time.time()
        needs_flush = False
        
        lock = self._get_lock()
        async with lock:
            # Check dedup
            last_sent = self._sent_dedup.get(dedup_key, 0)
            if now - last_sent < DEDUP_WINDOW:
                self._metrics["deduped"] += 1
                logger.debug("Email deduped | to=%s subject=%s", to, subject)
                return False
            
            # Check queue size
            if len(self._queue) >= MAX_QUEUE_SIZE:
                logger.warning("Queue full (%d) — forcing flush", len(self._queue))
                needs_flush = True
            
            # Add to queue (sorted by priority)
            email = QueuedEmail(
                priority=priority,
                queued_at=now,
                to=to,
                subject=subject,
                html=html,
                send_fn=send_fn,
                send_kwargs=send_kwargs,
            )
            self._queue.append(email)
            self._queue.sort()  # Sort by priority
            self._sent_dedup[dedup_key] = now
            self._metrics["queued"] += 1
            
            logger.debug(
                "Email queued | to=%s priority=%s queue_size=%d",
                to, priority.name, len(self._queue)
            )
            
            if len(self._queue) >= BATCH_SIZE:
                needs_flush = True
        
        # Flush outside lock
        if needs_flush:
            await self._flush()
        
        return True

    # ── Background loops ──────────────────────────────────────────────────────
    
    async def _flush_loop(self) -> None:
        """Periodic flush every FLUSH_INTERVAL seconds"""
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            await self._flush()

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old dedup entries"""
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL)
            await self._cleanup_dedup()

    async def _cleanup_dedup(self) -> None:
        """Remove expired dedup entries to prevent memory leak"""
        lock = self._get_lock()
        async with lock:
            now = time.time()
            old_count = len(self._sent_dedup)
            self._sent_dedup = {
                k: v for k, v in self._sent_dedup.items()
                if now - v < DEDUP_WINDOW
            }
            removed = old_count - len(self._sent_dedup)
            if removed > 0:
                logger.debug("Dedup cleanup | removed=%d remaining=%d", removed, len(self._sent_dedup))

    # ── Flush ─────────────────────────────────────────────────────────────────
    
    async def _flush(self) -> None:
        """Send all queued emails (batch)"""
        lock = self._get_lock()
        
        # ── Extract batch ──────────────────────────────────────────────────────
        async with lock:
            if not self._queue:
                return
            
            batch = self._queue[:]
            self._queue.clear()
            self._metrics["flushed_batches"] += 1
        
        # ── Send outside lock ──────────────────────────────────────────────────
        logger.info("Flushing email queue | batch=%d", len(batch))
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        for email in batch:
            try:
                if loop:
                    await loop.run_in_executor(
                        None,
                        email.send_fn,
                        **email.send_kwargs
                    )
                else:
                    email.send_fn(**email.send_kwargs)
                
                self._metrics["sent"] += 1
                logger.info(
                    "✓ Queued email sent | to=%s subject=%s priority=%s",
                    email.to, email.subject, email.priority.name
                )
            except Exception as exc:
                self._metrics["failed"] += 1
                logger.error(
                    "✗ Queued email failed | to=%s subject=%s: %s",
                    email.to, email.subject, exc
                )

    # ── Sync flush (for shutdown) ─────────────────────────────────────────────
    
    def flush_sync(self) -> int:
        """
        Synchronous flush for non-async contexts (app shutdown).
        Returns count of emails sent.
        """
        batch = self._queue[:]
        self._queue.clear()
        
        if not batch:
            return 0
        
        logger.info("Sync flushing email queue | count=%d", len(batch))
        sent = 0
        
        for email in batch:
            try:
                email.send_fn(**email.send_kwargs)
                sent += 1
                self._metrics["sent"] += 1
            except Exception as exc:
                self._metrics["failed"] += 1
                logger.error("Sync flush failed | to=%s: %s", email.to, exc)
        
        return sent

    # ── Metrics ───────────────────────────────────────────────────────────────
    
    def get_metrics(self) -> dict[str, int]:
        """Get queue statistics"""
        return {
            **self._metrics,
            "queue_depth": len(self._queue),
            "dedup_entries": len(self._sent_dedup),
        }

    def get_queue_depth(self) -> int:
        """Current number of emails in queue"""
        return len(self._queue)


# ══════════════════════════════════════════════════════════════════════════════
#  SINGLETON
# ══════════════════════════════════════════════════════════════════════════════

_queue = EmailQueue()


def get_email_queue() -> EmailQueue:
    """Get the global email queue instance"""
    return _queue


# ══════════════════════════════════════════════════════════════════════════════
#  CONVENIENCE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def queue_email(
    to: str,
    subject: str,
    html: str,
    send_fn: Callable,
    priority: EmailPriority = EmailPriority.NORMAL,
) -> bool:
    """Convenience function to queue an email"""
    return await get_email_queue().enqueue(to, subject, html, send_fn, priority=priority)


async def send_immediate_email(
    to: str,
    subject: str,
    html: str,
    send_fn: Callable,
) -> bool:
    """Send email immediately (bypasses queue)"""
    return await get_email_queue().enqueue(
        to, subject, html, send_fn,
        priority=EmailPriority.IMMEDIATE,
    )