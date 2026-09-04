"""
Audit Log
=========
Path: app/logs/audit.py

Persists admin actions for compliance and traceability.
Called from every admin-only write endpoint.

Standard row shape (shared with security.py):
    timestamp, actor_id, actor_role, action, entity_type, entity_id,
    old_value, new_value, ip_address, request_id, metadata (jsonb)
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


async def log_admin_action(
    actor_id: str,
    actor_role: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    old_value: Any = None,
    new_value: Any = None,
    ip_address: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Write a single audit log row.

    Called from admin write endpoints to record who changed what.
    Failures are logged but never raised — audit logging must not
    break the request that triggered it.
    """
    admin_sb = await get_async_admin_supabase()
    try:
        await admin_sb.table("audit_log").insert({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_id": actor_id,
            "actor_role": actor_role,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "old_value": old_value,
            "new_value": new_value,
            "ip_address": ip_address,
            "request_id": request_id,
            "metadata": metadata or {},
        }).execute()
        logger.info(
            "[AUDIT] %s by %s (%s) on %s/%s",
            action,
            actor_id[:8] if actor_id else "UNKNOWN",
            actor_role,
            entity_type,
            entity_id[:8] if entity_id else "N/A",
        )
    except Exception as exc:
        logger.error(
            "[AUDIT] Failed to write audit log: %s (action=%s, actor=%s, entity=%s/%s)",
            exc,
            action,
            actor_id[:8] if actor_id else "UNKNOWN",
            entity_type,
            entity_id[:8] if entity_id else "N/A",
            exc_info=True,
        )
