"""Durable retry worker for failed web-push deliveries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging

from app.core.supabase import get_async_admin_supabase
from app.integrations.push.webpush_impl import _endpoint_key, send_push

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 8


async def retry_notification_dlq(limit: int = 50) -> int:
    sb = await get_async_admin_supabase()
    now = datetime.now(timezone.utc)

    result = await (
        sb.table("notification_dlq")
        .select("*")
        .eq("status", "failed")
        .lte("next_retry_at", now.isoformat())
        .order("created_at")
        .limit(limit)
        .execute()
    )
    rows = list(getattr(result, "data", None) or [])
    resolved = 0

    for row in rows:
        row_id = str(row.get("id"))
        attempt = int(row.get("attempt_count") or 0) + 1
        claim = await (
            sb.table("notification_dlq")
            .update({"status": "retrying", "attempt_count": attempt})
            .eq("id", row_id)
            .eq("status", "failed")
            .select("id")
            .execute()
        )
        if not getattr(claim, "data", None):
            continue

        try:
            user_id = row.get("user_id")
            endpoint_hash = row.get("subscription_endpoint_hash")
            if not user_id or not endpoint_hash:
                raise RuntimeError("Notification retry record has no user/endpoint key")

            subs_result = await (
                sb.table("push_subscriptions")
                .select("id,endpoint,subscription_json")
                .eq("user_id", user_id)
                .execute()
            )
            subscription = None
            for sub_row in list(getattr(subs_result, "data", None) or []):
                endpoint = str(sub_row.get("endpoint") or "")
                if endpoint and _endpoint_key(endpoint) == endpoint_hash:
                    subscription = json.loads(sub_row.get("subscription_json") or "{}")
                    break

            if not subscription or not subscription.get("endpoint"):
                await (
                    sb.table("notification_dlq")
                    .update(
                        {
                            "status": "resolved",
                            "resolved_at": now.isoformat(),
                            "error_message": "Subscription no longer exists; retry resolved.",
                        }
                    )
                    .eq("id", row_id)
                    .execute()
                )
                resolved += 1
                continue

            push_result = send_push(
                subscription,
                str(row.get("title") or "Luviio"),
                str(row.get("body") or ""),
                url=str(row.get("target_url") or "/"),
            )

            if push_result in ("sent", "dead"):
                if push_result == "dead":
                    await sb.table("push_subscriptions").delete().eq("endpoint", subscription["endpoint"]).execute()
                await (
                    sb.table("notification_dlq")
                    .update(
                        {
                            "status": "resolved",
                            "resolved_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": None,
                        }
                    )
                    .eq("id", row_id)
                    .execute()
                )
                resolved += 1
                continue

            if attempt >= _MAX_ATTEMPTS:
                await (
                    sb.table("notification_dlq")
                    .update(
                        {
                            "status": "failed",
                            "next_retry_at": None,
                            "error_message": "Push delivery exhausted retry budget.",
                        }
                    )
                    .eq("id", row_id)
                    .execute()
                )
            else:
                next_retry = datetime.now(timezone.utc) + timedelta(seconds=min(900, 2 ** min(attempt, 9)))
                await (
                    sb.table("notification_dlq")
                    .update(
                        {
                            "status": "failed",
                            "next_retry_at": next_retry.isoformat(),
                            "error_message": "Push delivery failed; scheduled for retry.",
                        }
                    )
                    .eq("id", row_id)
                    .execute()
                )
        except Exception as exc:
            logger.exception("Notification DLQ retry failed | id=%s", row_id)
            next_retry = datetime.now(timezone.utc) + timedelta(seconds=min(900, 2 ** min(attempt, 9)))
            await (
                sb.table("notification_dlq")
                .update(
                    {
                        "status": "failed",
                        "next_retry_at": None if attempt >= _MAX_ATTEMPTS else next_retry.isoformat(),
                        "error_message": str(exc)[:1000],
                    }
                )
                .eq("id", row_id)
                .execute()
            )

    return resolved
