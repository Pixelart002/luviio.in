"""
Dynamic Permission Overrides (DB-driven RBAC toggles)
======================================================
Path: app/permissions/overrides.py

Lets an admin enable/disable individual permissions per role at runtime
without a redeploy. The source of truth for the DEFAULT matrix stays in
``app/permissions/base.ROLE_PERMISSIONS``; this module layers an optional
``role_permissions`` table on top:

  * No row for (role, permission)  -> fall back to the static default.
  * Row present with enabled=true  -> explicit grant (overrides static deny).
  * Row present with enabled=false -> explicit deny (overrides static grant).

The ``super_admin`` wildcard ("*") can never be narrowed from the DB — God
Mode stays absolute.

Cache is TTL-based (in-memory) and shared process-wide. If the table is
missing/unreachable this module degrades gracefully to the static matrix so
the app always boots.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60
# Maps (role, permission) -> bool (True = enabled, False = disabled)
_override_cache: dict[tuple[str, str], bool] = {}
_cache_ts: float = 0.0
_loaded = False


def invalidate_overrides_cache() -> None:
    """Called after any toggle mutation so the next access re-reads the table."""
    global _cache_ts, _loaded
    _override_cache.clear()
    _cache_ts = 0.0
    _loaded = False


async def _reload_overrides() -> bool:
    """Loads the override matrix into memory. Returns True on success."""
    global _override_cache, _cache_ts, _loaded
    if _loaded and (time.time() - _cache_ts) < _CACHE_TTL_SECONDS:
        return True
    try:
        from app.core.supabase import get_async_admin_supabase
        sb = await get_async_admin_supabase()
        res = await sb.table("role_permissions").select("role, permission, enabled").execute()
        rows = getattr(res, "data", None) or []
        _override_cache = {
            (r.get("role"), r.get("permission")): bool(r.get("enabled"))
            for r in rows if r.get("role") and r.get("permission")
        }
        _cache_ts = time.time()
        _loaded = True
        return True
    except Exception as exc:  # table missing / network issue -> static fallback
        logger.warning("[RBAC:OVERRIDES] Could not load role_permissions (%s). Using static matrix.", exc)
        _override_cache = {}
        _cache_ts = time.time()
        _loaded = True
        return False


async def get_effective_permissions(role: str, static_base: set[str]) -> set[str]:
    """
    Returns the effective permission set for a role after applying DB overrides.
    ``static_base`` is the role's default permission set from ROLE_PERMISSIONS.
    """
    if "*" in static_base:
        return {"*"}  # super_admin God-Mode is absolute — cannot be narrowed.

    await _reload_overrides()

    effective = set(static_base)
    for (r, perm), enabled in _override_cache.items():
        if r != role:
            continue
        if enabled:
            effective.add(perm)
        else:
            effective.discard(perm)
    return effective


# Re-exported for convenience in router/guard code.
def static_descriptions() -> dict[str, Any]:
    """Human-readable catalogue of every permission in the system (for the admin UI)."""
    from app.enums.roles import UserRole
    from app.permissions import coupons, shipping, subscriptions, settings, products, orders, users, payments, admin
    groups = [
        ("products", products.ProductPermissions, "Product catalogue"),
        ("orders", orders.OrderPermissions, "Orders lifecycle"),
        ("users", users.UserPermissions, "Customer & staff accounts"),
        ("payments", payments.PaymentPermissions, "Payments & refunds"),
        ("settings", settings.SettingsPermissions, "System settings"),
        ("admin", admin.AdminPermissions, "Admin console"),
        ("coupons", coupons.CouponPermissions, "Discount coupons"),
        ("shipping", shipping.ShippingPermissions, "Shipping methods"),
        ("subscriptions", subscriptions.SubscriptionPermissions, "Subscription plans & tiers"),
    ]
    cat: dict[str, Any] = {}
    for group, cls, label in groups:
        perms = {k: v for k, v in vars(cls).items() if not k.startswith("_") and isinstance(v, str)}
        cat[group] = {"label": label, "permissions": perms}
    return {
        "roles": [r.value if hasattr(r, "value") else str(r) for r in UserRole],
        "categories": cat,
        "note": "super_admin ('*') has every permission and cannot be narrowed at runtime.",
    }
