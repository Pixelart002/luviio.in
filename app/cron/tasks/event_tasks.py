"""Durable application event and notification retry cron tasks."""
from __future__ import annotations

import logging

from app.cron.registry import cron_task
from app.events.bus import get_event_bus
from app.integrations.push.dlq_retry import retry_notification_dlq

logger = logging.getLogger(__name__)


@cron_task(seconds=15, max_instances=1, coalesce=True)
async def dispatch_event_outbox() -> None:
    try:
        processed = await get_event_bus().dispatch_outbox(limit=50)
        if processed:
            logger.info("[EVENT OUTBOX] Dispatched %d durable events", processed)
    except Exception:
        logger.exception("[EVENT OUTBOX] Dispatcher run failed")


@cron_task(seconds=30, max_instances=1, coalesce=True)
async def retry_notification_dlq_job() -> None:
    try:
        resolved = await retry_notification_dlq(limit=50)
        if resolved:
            logger.info("[NOTIFICATION DLQ] Resolved %d failed deliveries", resolved)
    except Exception:
        logger.exception("[NOTIFICATION DLQ] Retry run failed")
