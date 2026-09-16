"""
Settings Event Handlers
======================
Path: app/events/handlers/settings_handlers.py

Persists audit rows for settings changes using the canonical
`settings_audit_log` schema.
"""
import logging

from app.core.supabase import get_async_admin_supabase
from app.events.settings_events import SettingResetEvent, SettingUpdatedEvent

logger = logging.getLogger(__name__)


async def _write_audit_row(payload: dict) -> None:
    admin_sb = await get_async_admin_supabase()
    await admin_sb.table("settings_audit_log").insert(payload).execute()


async def handle_setting_updated(event: SettingUpdatedEvent) -> None:
    """Persist a settings audit row when a setting is updated."""
    try:
        await _write_audit_row({
            "action": "updated",
            "key": event.key,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "changed_by": event.updated_by,
            "reason": event.reason,
        })
        logger.info("Settings audit written | action=updated key=%s", event.key)
    except Exception:
        logger.exception("Settings audit write failed | action=updated key=%s", event.key)
        raise


async def handle_setting_reset(event: SettingResetEvent) -> None:
    """Persist a settings audit row when a setting is reset to default."""
    try:
        await _write_audit_row({
            "action": "reset",
            "key": event.key,
            "old_value": None,
            "new_value": event.restored_value,
            "changed_by": event.reset_by,
            "reason": "reset_to_default",
        })
        logger.info("Settings audit written | action=reset key=%s", event.key)
    except Exception:
        logger.exception("Settings audit write failed | action=reset key=%s", event.key)
        raise
