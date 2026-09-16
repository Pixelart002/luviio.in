"""Durable application-event outbox persistence."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


async def enqueue_event(*, event_id: str, event_type: str, payload: dict[str, Any]) -> None:
    sb = await get_async_admin_supabase()
    await (
        sb.table("event_outbox")
        .insert(
            {
                "id": event_id,
                "event_type": event_type,
                "payload": payload,
                "status": "pending",
                "attempts": 0,
                "next_retry_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .execute()
    )


async def fetch_pending(limit: int = 50) -> list[dict[str, Any]]:
    sb = await get_async_admin_supabase()
    result = await (
        sb.table("event_outbox")
        .select("id,event_type,payload,attempts")
        .eq("status", "pending")
        .lte("next_retry_at", datetime.now(timezone.utc).isoformat())
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return list(getattr(result, "data", None) or [])


async def claim_event(event_id: str) -> dict[str, Any] | None:
    sb = await get_async_admin_supabase()
    now = datetime.now(timezone.utc).isoformat()
    result = await (
        sb.table("event_outbox")
        .update(
            {
                "status": "processing",
                "attempts": 1,
                "locked_at": now,
            }
        )
        .eq("id", event_id)
        .eq("status", "pending")
        .execute()
    )
    rows = list(getattr(result, "data", None) or [])
    return rows[0] if rows else {"id": event_id}


async def mark_completed(event_id: str) -> None:
    sb = await get_async_admin_supabase()
    await (
        sb.table("event_outbox")
        .update(
            {
                "status": "completed",
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "locked_at": None,
                "last_error": None,
            }
        )
        .eq("id", event_id)
        .execute()
    )


async def mark_retry(
    event_id: str,
    *,
    attempt: int,
    error: str,
    max_attempts: int = 8,
) -> None:
    sb = await get_async_admin_supabase()
    if attempt >= max_attempts:
        status = "failed"
        next_retry_at = None
    else:
        delay_seconds = min(900, 2 ** min(attempt, 9))
        next_retry_at = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + delay_seconds,
            tz=timezone.utc,
        ).isoformat()
        status = "pending"

    await (
        sb.table("event_outbox")
        .update(
            {
                "status": status,
                "attempts": attempt,
                "next_retry_at": next_retry_at,
                "locked_at": None,
                "last_error": error[:1000],
            }
        )
        .eq("id", event_id)
        .execute()
    )


async def recover_stale_processing(timeout_seconds: int = 300) -> int:
    sb = await get_async_admin_supabase()
    cutoff = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - timeout_seconds,
        tz=timezone.utc,
    ).isoformat()
    result = await (
        sb.table("event_outbox")
        .update(
            {
                "status": "pending",
                "next_retry_at": datetime.now(timezone.utc).isoformat(),
                "locked_at": None,
            }
        )
        .eq("status", "processing")
        .lt("locked_at", cutoff)
        .execute()
    )
    return len(getattr(result, "data", None) or [])
