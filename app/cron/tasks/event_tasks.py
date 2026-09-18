"""Durable application event and notification retry cron tasks."""
from __future__ import annotations

import asyncio
import logging

from app.cron.registry import cron_task
from app.events.bus import get_event_bus
from app.integrations.push.dlq_retry import retry_notification_dlq

logger = logging.getLogger(__name__)

_CRON_TIMEOUT_SECONDS = 20
_BATCH_SIZE = 20


@cron_task(seconds=15, max_instances=1, coalesce=True)
async def dispatch_event_outbox() -> None:
    try:
        processed = await asyncio.wait_for(
            get_event_bus().dispatch_outbox(limit=_BATCH_SIZE),
            timeout=_CRON_TIMEOUT_SECONDS,
        )
        if processed:
            logger.info("[EVENT OUTBOX] Dispatched %d durable events", processed)
    except asyncio.TimeoutError:
        logger.error(
            "[EVENT OUTBOX] Dispatcher timed out after %ss; next run will continue from durable claims",
            _CRON_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("[EVENT OUTBOX] Dispatcher run failed")


@cron_task(seconds=30, max_instances=1, coalesce=True)
async def retry_notification_dlq_job() -> None:
    try:
        resolved = await asyncio.wait_for(
            retry_notification_dlq(limit=_BATCH_SIZE),
            timeout=_CRON_TIMEOUT_SECONDS,
        )
        if resolved:
            logger.info("[NOTIFICATION DLQ] Resolved %d failed deliveries", resolved)
    except asyncio.TimeoutError:
        logger.error(
            "[NOTIFICATION DLQ] Retry timed out after %ss; next run will continue from durable state",
            _CRON_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("[NOTIFICATION DLQ] Retry run failed")
