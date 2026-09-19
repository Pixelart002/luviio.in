"""Persistence for provider-managed shipments."""
from __future__ import annotations

from typing import Any, Optional

from app.core.supabase import get_async_admin_supabase


class ShippingProviderRepository:
    async def get_by_order(self, order_id: str, provider_key: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        res = await (
            sb.table("shipping_shipments")
            .select("*")
            .eq("order_id", order_id)
            .eq("provider_key", provider_key)
            .maybe_single()
            .execute()
        )
        return res.data if res else None

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        sb = await get_async_admin_supabase()
        res = await sb.table("shipping_shipments").insert(data).select("*").single().execute()
        return res.data

    async def update(self, shipment_id: str, data: dict[str, Any]) -> dict[str, Any]:
        sb = await get_async_admin_supabase()
        res = await (
            sb.table("shipping_shipments")
            .update(data)
            .eq("id", shipment_id)
            .select("*")
            .single()
            .execute()
        )
        return res.data
