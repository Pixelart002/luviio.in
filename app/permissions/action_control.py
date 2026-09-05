"""
User Action Controls — shared per-user capability gate
=======================================================
Path: app/permissions/action_control.py

The "big-software" control layer: beyond role permissions, an admin (or an
automated policy) can DISABLE a specific capability for a specific user.
Example: a user whose subscription payment was never received gets
`checkout` / `subscription_upgrade` / `access_premium_products` disabled.

Storage: `user_action_controls(user_id, action, enabled, reason, updated_by)`.
Default (no row) = ENABLED. Only an explicit row with enabled=false blocks.

This is shared security infrastructure — called from coupon, checkout and
subscription code — so it lives alongside the other permission engines in
`app/permissions/`, not inside any single domain.
"""
from __future__ import annotations

import logging
import time

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 45
# (user_id, action) -> bool
_control_cache: dict[tuple[str, str], bool] = {}
_cache_ts: float = 0.0
_loaded = False


def invalidate_action_control_cache() -> None:
    global _cache_ts, _loaded
    _control_cache.clear()
    _cache_ts = 0.0
    _loaded = False


async def _reload() -> None:
    global _control_cache, _cache_ts, _loaded
    if _loaded and (time.time() - _cache_ts) < _CACHE_TTL_SECONDS:
        return
    try:
        from app.core.supabase import get_async_admin_supabase
        sb = await get_async_admin_supabase()
        res = await sb.table("user_action_controls").select("user_id, action, enabled").execute()
        rows = getattr(res, "data", None) or []
        _control_cache = {
            (r.get("user_id"), r.get("action")): bool(r.get("enabled"))
            for r in rows if r.get("user_id") and r.get("action")
        }
        _cache_ts = time.time()
        _loaded = True
    except Exception as exc:
        logger.warning("[RBAC:ACTION] Could not load user_action_controls (%s). Allowing by default.", exc)
        _control_cache = {}
        _cache_ts = time.time()
        _loaded = True


async def is_action_enabled(user_id: str, action: str) -> bool:
    """True unless an explicit disabled row exists for (user_id, action)."""
    await _reload()
    return _control_cache.get((user_id, action), True)


async def assert_action_enabled(user_id: str, action: str, reason: str = "") -> None:
    """Raises 403 if the action is disabled for this user."""
    if not user_id:
        return
    if not await is_action_enabled(user_id, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=reason or f"Action '{action}' is currently disabled for your account.",
        )
