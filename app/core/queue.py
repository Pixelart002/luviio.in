"""
Email Batch Queue — Production Grade
=====================================
Path: app/core/queue.py
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable
from functools import partial

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
FLUSH_INTERVAL = 30
DEDUP_WINDOW = 300
MAX_QUEUE_SIZE = 100
CLEANUP_INTERVAL = 600

class EmailPriority(IntEnum):
    IMMEDIATE = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3

@dataclass
class QueuedEmail:
    priority: EmailPriority = field(default=EmailPriority.NORMAL)
    queued_at: float = field(default_factory=time.time)
    to: str = field(default="")
    subject: str = field(default="")
    html: str = field(default="")
    send_fn: Callable = field(default=lambda: None)
    send_kwargs: dict = field(default_factory=dict)

class EmailQueue:
    def __init__(self) -> None:
        self._queue: list[QueuedEmail] = []
        self._sent_dedup: dict[str, float] = {}
        self._lock: asyncio.Lock | None = None
        self._flush_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._metrics = {"queued": 0, "sent": 0, "failed": 0, "deduped": 0, "immediate": 0, "flushed_batches": 0}
        self._started = False

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None: self._lock = asyncio.Lock()
        return self._lock

    def start(self) -> None:
        if self._started: return
        try:
            loop = asyncio.get_running_loop()
            self._flush_task = loop.create_task(self._flush_loop())
            self._cleanup_task = loop.create_task(self._cleanup_loop())
            self._started = True
        except RuntimeError:
            logger.warning("No running event loop — email queue in sync-only mode")

    async def stop(self) -> None:
        if self._flush_task: self._flush_task.cancel()
        if self._cleanup_task: self._cleanup_task.cancel()
        await self._flush()
        self._started = False

    async def enqueue(self, to: str, subject: str, html: str, send_fn: Callable, *, priority: EmailPriority = EmailPriority.NORMAL, **send_kwargs) -> bool:
        if priority == EmailPriority.IMMEDIATE:
            self._metrics["immediate"] += 1
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, partial(send_fn, **send_kwargs))
                self._metrics["sent"] += 1
                return True
            except Exception:
                self._metrics["failed"] += 1
                return False
        
        dedup_key = f"{to}|{subject}"
        now = time.time()
        needs_flush = False
        
        lock = self._get_lock()
        async with lock:
            last_sent = self._sent_dedup.get(dedup_key, 0)
            if now - last_sent < DEDUP_WINDOW:
                self._metrics["deduped"] += 1
                return False
            
            if len(self._queue) >= MAX_QUEUE_SIZE: needs_flush = True
            
            self._queue.append(QueuedEmail(priority=priority, queued_at=now, to=to, subject=subject, html=html, send_fn=send_fn, send_kwargs=send_kwargs))
            self._queue.sort(key=lambda x: (x.priority.value, x.queued_at))
            self._sent_dedup[dedup_key] = now
            self._metrics["queued"] += 1
            
            if len(self._queue) >= BATCH_SIZE: needs_flush = True
        
        if needs_flush: await self._flush()
        return True

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            await self._flush()

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL)
            await self._cleanup_dedup()

    async def _cleanup_dedup(self) -> None:
        lock = self._get_lock()
        async with lock:
            now = time.time()
            self._sent_dedup = {k: v for k, v in self._sent_dedup.items() if now - v < DEDUP_WINDOW}

    async def _flush(self) -> None:
        lock = self._get_lock()
        async with lock:
            if not self._queue: return
            batch = self._queue[:]
            self._queue.clear()
            self._metrics["flushed_batches"] += 1
        
        try: loop = asyncio.get_running_loop()
        except RuntimeError: loop = None
        
        for email in batch:
            try:
                if loop: await loop.run_in_executor(None, partial(email.send_fn, **email.send_kwargs))
                else: email.send_fn(**email.send_kwargs)
                self._metrics["sent"] += 1
            except Exception:
                self._metrics["failed"] += 1

_queue = EmailQueue()
def get_email_queue() -> EmailQueue: return _queue

async def queue_email(to: str, subject: str, html: str, send_fn: Callable, priority: EmailPriority = EmailPriority.NORMAL) -> bool:
    return await get_email_queue().enqueue(to, subject, html, send_fn, priority=priority)