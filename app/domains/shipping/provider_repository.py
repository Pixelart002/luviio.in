"""Persistence for provider-managed shipments and provider events."""
from __future__ import annotations
from typing import Any, Optional
from app.core.supabase import get_async_admin_supabase

class ShippingProviderRepository:
    async def get_by_order(self, order_id: str, provider_key: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        res = await (sb.table("shipping_shipments").select("*").eq("order_id", order_id).eq("provider_key", provider_key).maybe_single().execute())
        return res.data if res else None

    async def get(self, shipment_id: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        res = await sb.table("shipping_shipments").select("*").eq("id", shipment_id).maybe_single().execute()
        return res.data if res else None

    async def list_recent(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        q = sb.table("shipping_shipments").select("*, orders(order_number,status,customer_id,shipping_name,shipping_city,shipping_postal_code,total_amount,payment_method)").order("created_at", desc=True).limit(min(max(limit, 1), 200))
        if status:
            q = q.eq("status", status)
        res = await q.execute()
        return list(res.data or [])

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        sb = await get_async_admin_supabase()
        res = await sb.table("shipping_shipments").insert(data).select("*").single().execute()
        return res.data

    async def update(self, shipment_id: str, data: dict[str, Any]) -> dict[str, Any]:
        sb = await get_async_admin_supabase()
        res = await sb.table("shipping_shipments").update(data).eq("id", shipment_id).select("*").single().execute()
        return res.data

    async def record_event(self, shipment_id: str, provider_event_id: str, provider_status: str, payload: dict[str, Any], occurred_at: str | None = None) -> bool:
        sb = await get_async_admin_supabase()
        data = {
            "shipment_id": shipment_id,
            "provider_event_id": provider_event_id,
            "provider_status": provider_status,
            "payload": payload,
        }
        if occurred_at:
            data["occurred_at"] = occurred_at
        try:
            await sb.table("shipping_shipment_events").insert(data).execute()
            return True
        except Exception as exc:
            # Unique provider_event_id makes webhook delivery idempotent.
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                return False
            raise
