"""Coupon lifecycle maintenance tasks."""
from __future__ import annotations

import logging

from app.core.supabase import get_async_admin_supabase
from app.cron.registry import cron_task

logger = logging.getLogger(__name__)


@cron_task(minutes=5, max_instances=1, coalesce=True)
async def cleanup_expired_coupon_reservations() -> None:
    try:
        sb = await get_async_admin_supabase()
        res = await sb.rpc("cleanup_expired_coupon_reservations").execute()
        deleted = int(res.data or 0)
        if deleted:
            logger.info("[COUPON] Expired reservations cleaned | count=%s", deleted)
    except Exception:
        logger.exception("[COUPON] Expired reservation cleanup failed")
