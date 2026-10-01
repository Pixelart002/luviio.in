"""Manual shipping fulfillment service.

External courier APIs are intentionally absent from the production checkout path.
Luviio records shipping as manual and allows staff to manage tracking details
through the existing order/shipping administration flow.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.supabase import get_async_admin_supabase
from app.domains.shipping.provider_repository import ShippingProviderRepository
from app.domains.shipping.service import ShippingService

MANUAL_PROVIDER = "manual"


class ShippingProviderService:
    def __init__(self) -> None:
        self.repo = ShippingProviderRepository()

    async def serviceability(
        self,
        provider_key: str,
        pickup_postcode: str,
        delivery_postcode: str,
        weight_kg: float,
        cod: bool,
        declared_value: float | None = None,
    ) -> dict[str, Any]:
        if (provider_key or MANUAL_PROVIDER).strip().lower() != MANUAL_PROVIDER:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="External shipping providers are disabled. Shipping is handled manually.")
        return {
            "provider": MANUAL_PROVIDER,
            "serviceable": True,
            "shipping_mode": MANUAL_PROVIDER,
            "pickup_postcode": str(pickup_postcode or ""),
            "delivery_postcode": str(delivery_postcode or ""),
            "weight_kg": float(weight_kg or 0),
            "cod": bool(cod),
            "declared_value": declared_value,
        }

    async def quote_for_checkout(
        self,
        delivery_postcode: str,
        weight_kg: float,
        cod: bool,
        declared_value: float | None = None,
        selected_courier_id: int | None = None,
    ) -> dict[str, Any]:
        """Return the manual-shipping checkout contract without external API calls."""
        delivery_postcode = str(delivery_postcode or "").strip()
        if not delivery_postcode.isdigit() or len(delivery_postcode) != 6:
            raise HTTPException(status_code=422, detail="A valid 6-digit delivery PIN code is required.")
        rate = await ShippingService().compute_rate(
            subtotal=float(declared_value or 0),
            item_count=1,
            weight_kg=float(weight_kg or 0),
        )
        shipping_cost = float(rate.get("shipping_cost") or 0.0)
        selected = {
            "courier_id": None,
            "courier_name": "Manual shipping",
            "service_type": "manual",
            "delivery_mode": "manual",
            "vehicle_type": None,
            "shipping_cost": shipping_cost,
            "provider_rate": shipping_cost,
            "estimated_delivery_days": None,
            "free_shipping_threshold": rate.get("free_shipping_threshold"),
            "applied_type": rate.get("applied_type", "settings_default"),
        }
        return {
            "provider": MANUAL_PROVIDER,
            "shipping_mode": MANUAL_PROVIDER,
            "pickup_postcode": None,
            "delivery_postcode": delivery_postcode,
            "weight_kg": float(weight_kg or 0),
            "cod": bool(cod),
            "declared_value": declared_value,
            "selected": selected,
            "selection": "manual",
            "quotes": [selected],
            "couriers": [selected],
            "source": "manual",
            "stale": False,
            "retryable": False,
        }

    async def create_for_order(
        self,
        order_id: str,
        provider_key: str = MANUAL_PROVIDER,
        pickup_location: str | None = None,
        weight_kg: float | None = None,
        length_cm: float | None = None,
        breadth_cm: float | None = None,
        height_cm: float | None = None,
    ) -> dict[str, Any]:
        if (provider_key or MANUAL_PROVIDER).strip().lower() != MANUAL_PROVIDER:
            raise HTTPException(status_code=409, detail="External shipping providers are disabled. Shipping is handled manually.")
        sb = await get_async_admin_supabase()
        order_res = await (
            sb.table("orders")
            .select("id,status")
            .eq("id", str(order_id))
            .maybe_single()
            .execute()
        )
        order = order_res.data if order_res else None
        if not order:
            raise HTTPException(status_code=404, detail="Order not found.")

        order_status = str(order.get("status") or "").strip().lower()
        if order_status not in {"paid", "processing", "shipped", "delivered"}:
            raise HTTPException(
                status_code=409,
                detail="A manual shipment record can only be created for an active fulfillment order.",
            )

        existing = await self.repo.get_by_order(order_id, MANUAL_PROVIDER)
        if existing:
            return existing

        row = await self.repo.create({
            "order_id": order_id,
            "provider_key": MANUAL_PROVIDER,
            "status": "manual_pending",
            "metadata": {"shipping_mode": MANUAL_PROVIDER},
        })
        return row

    async def _manual_operation(self, operation: str) -> dict[str, Any]:
        raise HTTPException(status_code=409, detail=f"{operation} is unavailable in manual shipping mode. Update the order tracking details manually.")

    async def assign_awb(self, shipment_id: str, courier_id: int | None = None) -> dict[str, Any]:
        return await self._manual_operation("Courier/AWB assignment")

    async def process_shipment(self, shipment_id: str) -> dict[str, Any]:
        return await self._manual_operation("Provider shipment processing")

    async def schedule_pickup(self, shipment_id: str) -> dict[str, Any]:
        return await self._manual_operation("Provider pickup scheduling")

    async def generate_label(self, shipment_id: str) -> dict[str, Any]:
        return await self._manual_operation("Provider label generation")

    async def generate_manifest(self, shipment_id: str) -> dict[str, Any]:
        return await self._manual_operation("Provider manifest generation")

    async def print_invoice(self, shipment_id: str) -> dict[str, Any]:
        return await self._manual_operation("Provider invoice generation")

    async def sync_tracking(self, shipment_id: str) -> dict[str, Any]:
        row = await self.repo.get(shipment_id)
        if not row:
            raise HTTPException(status_code=404, detail="Shipment not found.")
        return row

    async def cancel(self, shipment_id: str) -> dict[str, Any]:
        row = await self.repo.get(shipment_id)
        if not row:
            raise HTTPException(status_code=404, detail="Shipment not found.")
        return await self.repo.update(shipment_id, {"status": "cancelled"})

    async def track(self, provider_key: str, tracking_number: str) -> dict[str, Any]:
        if (provider_key or MANUAL_PROVIDER).strip().lower() != MANUAL_PROVIDER:
            raise HTTPException(status_code=409, detail="External shipping providers are disabled.")
        sb = await get_async_admin_supabase()
        res = await sb.table("shipping_shipments").select("*").eq("provider_key", MANUAL_PROVIDER).eq("tracking_number", tracking_number.strip()).maybe_single().execute()
        return res.data if res and res.data else {"status": "not_found", "tracking_number": tracking_number.strip(), "shipping_mode": MANUAL_PROVIDER}

    async def handle_webhook(self, provider_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise HTTPException(status_code=410, detail="External shipping webhooks are disabled. Shipping is handled manually.")
