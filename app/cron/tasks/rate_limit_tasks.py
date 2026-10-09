"""Maintenance task for shared HTTP rate-limit buckets."""
from __future__ import annotations

import logging

from app.core.supabase import get_async_admin_supabase
from app.cron.registry import cron_task

logger = logging.getLogger(__name__)


@cron_task(hours=6, max_instances=1, coalesce=True)
async def cleanup_http_token_bucket_state_job() -> None:
    """Remove inactive shared HTTP token buckets older than 24 hours."""
    try:
        sb = await get_async_admin_supabase()
        result = await sb.rpc("cleanup_http_token_bucket_state", {}).execute()
        deleted = int(result.data or 0)
        if deleted:
            logger.info("[RATE LIMIT] Stale token buckets cleaned | count=%s", deleted)
        else:
            logger.debug("[RATE LIMIT] No stale token buckets to clean")
    except Exception:
        logger.exception("[RATE LIMIT] Token-bucket cleanup failed")
