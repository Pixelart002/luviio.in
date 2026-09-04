"""
Settings Event Handlers
======================
Path: app/events/handlers/settings_handlers.py

Rebuilt — was deleted, leaving SettingUpdatedEvent/SettingResetEvent with no subscribers.
The events are published by app/services/settings/core_engine.py.
These handlers persist audit log entries for settings changes.
"""
import logging
from typing import Any

from app.events.settings_events import SettingUpdatedEvent, SettingResetEvent
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


async def handle_setting_updated(event: SettingUpdatedEvent) -> None:
    """
    Persist a settings audit row when a setting is updated.
    Writes to the `settings_audit_log` table.
    """
    admin_sb = await get_async_admin_supabase()
    try:
        await admin_sb.table("settings_audit_log").insert({
            "action": "updated",
            "key": event.key,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "actor_id": event.updated_by,
            "reason": event.reason,
        }).execute()
        logger.info(
            "[HANDLER:SETTINGS] Audit log written for key='%s' by %s",
            event.key,
            event.updated_by,
        )
    except Exception as exc:
        logger.error(
            "[HANDLER:SETTINGS] Failed to write audit log for key='%s': %s",
            event.key,
            exc,
            exc_info=True,
        )


async def handle_setting_reset(event: SettingResetEvent) -> None:
    """
    Persist a settings audit row when a setting is reset to default.
    Writes to the `settings_audit_log` table.
    """
    admin_sb = await get_async_admin_supabase()
    try:
        await admin_sb.table("settings_audit_log").insert({
            "action": "reset",
            "key": event.key,
            "old_value": None,
            "new_value": event.restored_value,
            "actor_id": event.reset_by,
            "reason": "reset_to_default",
        }).execute()
        logger.info(
            "[HANDLER:SETTINGS] Audit log written for reset key='%s' by %s",
            event.key,
            event.reset_by,
        )
    except Exception as exc:
        logger.error(
            "[HANDLER:SETTINGS] Failed to write audit log for reset key='%s': %s",
            event.key,
            exc,
            exc_info=True,
        )
