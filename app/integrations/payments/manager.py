"""Runtime payment-plugin management.

Provider code is shipped with the application; database state controls which
installed providers/methods are active at runtime. Secrets are never accepted
by these management APIs.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.core.supabase import get_async_admin_supabase
from app.integrations.payments.registry import PAYMENT_REGISTRY


class PaymentPluginManager:
    """DB-backed lifecycle manager for installed payment providers."""

    async def list_plugins(self) -> List[Dict[str, Any]]:
        sb = await get_async_admin_supabase()
        res = await sb.table("payment_provider_plugins").select(
            "id,provider_key,display_name,enabled,priority,is_default,capabilities,created_at,updated_at"
        ).order("priority").order("display_name").execute()
        return getattr(res, "data", None) or []

    async def set_provider_enabled(self, provider_key: str, enabled: bool) -> Dict[str, Any]:
        key = provider_key.strip().lower()
        if key not in PAYMENT_REGISTRY:
            raise ValueError(f"Payment provider '{key}' is not installed.")
        sb = await get_async_admin_supabase()
        res = await sb.table("payment_provider_plugins").update({"enabled": enabled}).eq("provider_key", key).select(
            "id,provider_key,display_name,enabled,priority,is_default,capabilities"
        ).execute()
        data = getattr(res, "data", None) or []
        if not data:
            raise ValueError(f"Payment provider '{key}' is not configured.")
        return data[0]

    async def set_method_enabled(self, provider_key: str, method_key: str, enabled: bool) -> Dict[str, Any]:
        provider, method = provider_key.strip().lower(), method_key.strip().lower()
        sb = await get_async_admin_supabase()
        res = await sb.table("payment_provider_methods").update({"enabled": enabled}).eq("provider_key", provider).eq("method_key", method).select(
            "id,provider_key,method_key,display_name,enabled,priority,metadata"
        ).execute()
        data = getattr(res, "data", None) or []
        if not data:
            raise ValueError(f"Payment method '{method}' is not configured for '{provider}'.")
        return data[0]

    async def list_methods(self, provider_key: str | None = None) -> List[Dict[str, Any]]:
        sb = await get_async_admin_supabase()
        query = sb.table("payment_provider_methods").select(
            "id,provider_key,method_key,display_name,enabled,priority,metadata"
        ).order("provider_key").order("priority")
        if provider_key:
            query = query.eq("provider_key", provider_key.strip().lower())
        res = await query.execute()
        return getattr(res, "data", None) or []

    async def get_enabled_methods(self, provider_key: str) -> List[str]:
        provider = provider_key.strip().lower()
        sb = await get_async_admin_supabase()
        res = await sb.table("payment_provider_methods").select("method_key").eq(
            "provider_key", provider
        ).eq("enabled", True).order("priority").execute()
        return [str(row["method_key"]).strip().lower() for row in (getattr(res, "data", None) or []) if row.get("method_key")]

    async def register_installed_provider(self, provider_key: str, display_name: str, capabilities: Dict[str, Any], priority: int = 100) -> Dict[str, Any]:
        """Register an already-installed provider; never executes uploaded code."""
        key = provider_key.strip().lower()
        if key not in PAYMENT_REGISTRY:
            raise ValueError("Provider code is not installed in the application registry.")
        if not key or len(key) > 64 or not display_name.strip():
            raise ValueError("Invalid provider metadata.")
        sb = await get_async_admin_supabase()
        res = await sb.table("payment_provider_plugins").upsert(
            {"provider_key": key, "display_name": display_name.strip()[:120], "enabled": False, "priority": priority, "is_default": False, "capabilities": capabilities},
            on_conflict="provider_key",
        ).select("id,provider_key,display_name,enabled,priority,is_default,capabilities").execute()
        data = getattr(res, "data", None) or []
        if not data:
            raise ValueError("Provider registration returned no record.")
        return data[0]

    async def register_method(self, provider_key: str, method_key: str, display_name: str, priority: int = 100, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
        provider, method = provider_key.strip().lower(), method_key.strip().lower()
        if provider not in PAYMENT_REGISTRY:
            raise ValueError("Provider code is not installed in the application registry.")
        if not method or len(method) > 64 or not display_name.strip():
            raise ValueError("Invalid payment method metadata.")
        sb = await get_async_admin_supabase()
        provider_row = await sb.table("payment_provider_plugins").select("provider_key").eq("provider_key", provider).limit(1).execute()
        if not (getattr(provider_row, "data", None) or []):
            raise ValueError("Provider must be registered before adding methods.")
        res = await sb.table("payment_provider_methods").upsert(
            {"provider_key": provider, "method_key": method, "display_name": display_name.strip()[:120], "enabled": False, "priority": priority, "metadata": metadata or {}},
            on_conflict="provider_key,method_key",
        ).select("id,provider_key,method_key,display_name,enabled,priority,metadata").execute()
        data = getattr(res, "data", None) or []
        if not data:
            raise ValueError("Payment method registration returned no record.")
        return data[0]

    async def deactivate_provider(self, provider_key: str) -> Dict[str, Any]:
        """Deactivate a provider without deleting historical payment records."""
        return await self.set_provider_enabled(provider_key, False)

    async def get_active_provider(self, provider_key: str) -> Any:
        key = provider_key.strip().lower()
        if key not in PAYMENT_REGISTRY:
            raise ValueError(f"Payment provider '{key}' is not installed.")
        sb = await get_async_admin_supabase()
        res = await sb.table("payment_provider_plugins").select("enabled").eq("provider_key", key).limit(1).execute()
        data = getattr(res, "data", None) or []
        if not data or not data[0].get("enabled"):
            raise ValueError(f"Payment provider '{key}' is disabled.")
        return PAYMENT_REGISTRY[key]()
