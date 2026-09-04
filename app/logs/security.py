"""
Security Log
============
Path: app/logs/security.py

Persists security-relevant events: failed logins, rate-limit hits,
permission denials. Separate from access logs so they can be alerted
on independently.

Standard row shape (shared with audit.py):
    timestamp, actor_id, actor_role, action, entity_type, entity_id,
    old_value, new_value, ip_address, request_id, metadata (jsonb)
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


async def log_security_event(
    action: str,
    actor_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Write a single security log row.

    Called from auth failure paths, rate-limit middleware, and permission
    denial checks. Failures are logged but never raised — security logging
    must not break the request that triggered it.
    """
    admin_sb = await get_async_admin_supabase()
    try:
        await admin_sb.table("security_log").insert({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_id": actor_id,
            "actor_role": actor_role,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "old_value": None,
            "new_value": None,
            "ip_address": ip_address,
            "request_id": request_id,
            "metadata": metadata or {},
        }).execute()
        logger.info(
            "[SECURITY] %s by %s (%s) from %s",
            action,
            actor_id[:8] if actor_id else "UNKNOWN",
            actor_role or "unknown",
            ip_address or "unknown",
        )
    except Exception as exc:
        logger.error(
            "[SECURITY] Failed to write security log: %s (action=%s, actor=%s)",
            exc,
            action,
            actor_id[:8] if actor_id else "UNKNOWN",
            exc_info=True,
        )
