"""End-to-end shipment orchestration: order -> courier -> AWB -> pickup -> tracking."""
from __future__ import annotations
import hashlib, json, logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from app.core.supabase import get_async_admin_supabase
from app.integrations.shipping.registry import get_shipping_provider
from app.domains.shipping.provider_repository import ShippingProviderRepository
from app.events.bus import OrderShippedEvent, OrderStatusChangedEvent, get_event_bus
from app.integrations.push.webpush_impl import send_push_to_user

logger = logging.getLogger(__name__)

_SHIPPED_PROVIDER_STATUSES = {"picked_up", "in_transit", "out_for_delivery", "shipped", "dispatched"}
_DELIVERED_PROVIDER_STATUSES = {"delivered"}
_TERMINAL_PROVIDER_STATUSES = {"delivered", "cancelled", "canceled", "rto_delivered", "rto"}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _find(data: Any, *keys: str) -> Any:
    if isinstance(data, dict):
        for key in keys:
            if data.get(key) not in (None, ""):
                return data[key]
        for value in data.values():
            found = _find(value, *keys)
            if found not in (None, ""):
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find(value, *keys)
            if found not in (None, ""):
                return found
    return None

def _provider_status(data: dict[str, Any]) -> str:
    raw = _find(data, "current_status", "shipment_status", "status", "status_text")
    return str(raw or "").strip().lower().replace(" ", "_")

class ShippingProviderService:
    def __init__(self) -> None:
        self.repo = ShippingProviderRepository()

    async def serviceability(self, provider_key: str, pickup_postcode: str, delivery_postcode: str, weight_kg: float, cod: bool) -> dict[str, Any]:
        try:
            return await get_shipping_provider(provider_key).serviceability(
                pickup_postcode=pickup_postcode, delivery_postcode=delivery_postcode,
                weight_kg=weight_kg, cod=cod,
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Shipping provider unavailable: {provider_key}.") from exc

    async def create_for_order(self, order_id: str, provider_key: str, pickup_location: str, weight_kg: float, length_cm: float, breadth_cm: float, height_cm: float) -> dict[str, Any]:
        existing = await self.repo.get_by_order(order_id, provider_key)
        if existing:
            return existing
        sb = await get_async_admin_supabase()
        res = await (sb.table("orders").select("*, order_items(*, products(name, sku, hsn_code))").eq("id", order_id).maybe_single().execute())
        order = res.data if res else None
        if not order:
            raise HTTPException(status_code=404, detail="Order not found.")
        if str(order.get("status") or "").lower() in {"cancelled", "refunded"}:
            raise HTTPException(status_code=409, detail="Cancelled/refunded orders cannot be shipped.")

        items = order.get("order_items") or []
        payment_method = str(order.get("payment_method") or "").upper()
        provider_items = [{
            "name": item.get("product_name") or (item.get("products") or {}).get("name") or "Product",
            "sku": item.get("sku") or (item.get("products") or {}).get("sku") or str(item.get("product_id")),
            "units": int(item.get("quantity") or 1),
            "selling_price": float(item.get("unit_price") or 0),
            "discount": float(item.get("discount_amount") or 0),
            "tax": float(item.get("tax_amount") or 0),
            "hsn": str(item.get("hsn_code") or (item.get("products") or {}).get("hsn_code") or ""),
        } for item in items]
        shipping = {
            "name": order.get("shipping_name") or "", "phone": order.get("shipping_phone") or "",
            "email": order.get("shipping_email") or "", "address": order.get("shipping_line1") or "",
            "address_2": order.get("shipping_line2") or "", "city": order.get("shipping_city") or "",
            "state": order.get("shipping_state") or "", "country": order.get("shipping_country") or "India",
            "pincode": order.get("shipping_postal_code") or "",
        }
        first, *last = (shipping["name"] or "Customer").split()
        payload = {
            "order_id": order.get("order_number") or str(order_id), "order_date": order.get("created_at"),
            "pickup_location": pickup_location, "billing_customer_name": first, "billing_last_name": " ".join(last),
            "billing_address": shipping["address"], "billing_address_2": shipping["address_2"],
            "billing_city": shipping["city"], "billing_pincode": shipping["pincode"], "billing_state": shipping["state"],
            "billing_country": shipping["country"], "billing_email": shipping["email"], "billing_phone": shipping["phone"],
            "shipping_is_billing": True, "shipping_customer_name": first, "shipping_last_name": " ".join(last),
            "shipping_address": shipping["address"], "shipping_address_2": shipping["address_2"],
            "shipping_city": shipping["city"], "shipping_pincode": shipping["pincode"], "shipping_state": shipping["state"],
            "shipping_country": shipping["country"], "shipping_email": shipping["email"], "shipping_phone": shipping["phone"],
            "order_items": provider_items, "payment_method": "COD" if payment_method == "COD" else "Prepaid",
            "sub_total": float(order.get("subtotal") or 0), "length": length_cm, "breadth": breadth_cm,
            "height": height_cm, "weight": weight_kg,
        }
        try:
            response = await get_shipping_provider(provider_key).create_shipment(payload)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Unable to create shipment with provider.") from exc
        external_order_id = _find(response, "order_id", "orderid")
        external_shipment_id = _find(response, "shipment_id", "shipmentid", "id")
        if external_shipment_id is None:
            raise HTTPException(status_code=502, detail="Courier provider created no shipment identifier.")
        return await self.repo.create({
            "order_id": order_id, "provider_key": provider_key,
            "external_order_id": str(external_order_id) if external_order_id else None,
            "external_shipment_id": str(external_shipment_id),
            "status": "created", "provider_status": "created", "metadata": response,
        })

    async def _get_provider_row(self, shipment_id: str) -> dict[str, Any]:
        row = await self.repo.get(shipment_id)
        if not row:
            raise HTTPException(status_code=404, detail="Shipment not found.")
        return row

    async def assign_awb(self, shipment_id: str, courier_id: int | None = None) -> dict[str, Any]:
        row = await self._get_provider_row(shipment_id)
        if not row.get("external_shipment_id"):
            raise HTTPException(status_code=409, detail="Provider shipment must be created before AWB assignment.")
        try:
            response = await get_shipping_provider(row["provider_key"]).assign_awb(shipment_id=str(row["external_shipment_id"]), courier_id=courier_id)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Unable to assign courier/AWB.") from exc
        awb = _find(response, "awb_code", "awb", "tracking_number")
        courier = _find(response, "courier_name", "courier")
        if not awb:
            raise HTTPException(status_code=502, detail="Courier provider returned no AWB.")
        updated = await self.repo.update(shipment_id, {
            "tracking_number": str(awb), "courier_name": str(courier) if courier else row.get("courier_name"),
            "status": "awb_assigned", "provider_status": "awb_assigned", "metadata": {**(row.get("metadata") or {}), "awb_assignment": response},
            "updated_at": _now(),
        })
        return updated

    async def schedule_pickup(self, shipment_id: str) -> dict[str, Any]:
        row = await self._get_provider_row(shipment_id)
        if not row.get("tracking_number"):
            raise HTTPException(status_code=409, detail="Assign an AWB before scheduling pickup.")
        try:
            response = await get_shipping_provider(row["provider_key"]).generate_pickup(shipment_id=str(row["external_shipment_id"]))
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Unable to schedule courier pickup.") from exc
        pickup_id = _find(response, "pickup_id", "pickup_token", "pickupid")
        return await self.repo.update(shipment_id, {
            "pickup_id": str(pickup_id) if pickup_id else row.get("pickup_id"),
            "status": "pickup_scheduled", "provider_status": "pickup_scheduled",
            "pickup_scheduled_at": _now(), "metadata": {**(row.get("metadata") or {}), "pickup": response},
            "updated_at": _now(),
        })

    async def generate_label(self, shipment_id: str) -> dict[str, Any]:
        row = await self._get_provider_row(shipment_id)
        try: response = await get_shipping_provider(row["provider_key"]).generate_label(shipment_id=str(row["external_shipment_id"]))
        except Exception as exc: raise HTTPException(status_code=502, detail="Unable to generate shipping label.") from exc
        url = _find(response, "label_url", "label_download_url", "url")
        return await self.repo.update(shipment_id, {"label_url": str(url) if url else row.get("label_url"), "metadata": {**(row.get("metadata") or {}), "label": response}, "updated_at": _now()})

    async def generate_manifest(self, shipment_id: str) -> dict[str, Any]:
        row = await self._get_provider_row(shipment_id)
        try: response = await get_shipping_provider(row["provider_key"]).generate_manifest(shipment_id=str(row["external_shipment_id"]))
        except Exception as exc: raise HTTPException(status_code=502, detail="Unable to generate manifest.") from exc
        url = _find(response, "manifest_url", "manifest_download_url", "url")
        return await self.repo.update(shipment_id, {"manifest_url": str(url) if url else row.get("manifest_url"), "metadata": {**(row.get("metadata") or {}), "manifest": response}, "updated_at": _now()})

    async def print_invoice(self, shipment_id: str) -> dict[str, Any]:
        row = await self._get_provider_row(shipment_id)
        try: response = await get_shipping_provider(row["provider_key"]).print_invoice(shipment_id=str(row["external_shipment_id"]))
        except Exception as exc: raise HTTPException(status_code=502, detail="Unable to generate courier invoice.") from exc
        url = _find(response, "invoice_url", "invoice_download_url", "url")
        return await self.repo.update(shipment_id, {"provider_invoice_url": str(url) if url else row.get("provider_invoice_url"), "metadata": {**(row.get("metadata") or {}), "provider_invoice": response}, "updated_at": _now()})

    async def track(self, provider_key: str, tracking_number: str) -> dict[str, Any]:
        try: return await get_shipping_provider(provider_key).track(tracking_number)
        except Exception as exc: raise HTTPException(status_code=502, detail="Unable to fetch shipment tracking.") from exc

    async def sync_tracking(self, shipment_id: str) -> dict[str, Any]:
        row = await self._get_provider_row(shipment_id)
        awb = str(row.get("tracking_number") or "").strip()
        if not awb: raise HTTPException(status_code=409, detail="Shipment has no AWB.")
        response = await self.track(row["provider_key"], awb)
        return await self.apply_provider_event(row["provider_key"], response, shipment_id=shipment_id)

    async def apply_provider_event(self, provider_key: str, payload: dict[str, Any], shipment_id: str | None = None) -> dict[str, Any]:
        row = await self.repo.get(shipment_id) if shipment_id else None
        awb = str(_find(payload, "awb_code", "awb", "tracking_number") or "").strip()
        if not row and awb:
            sb = await get_async_admin_supabase()
            res = await sb.table("shipping_shipments").select("*").eq("provider_key", provider_key).eq("tracking_number", awb).maybe_single().execute()
            row = res.data if res else None
        if not row:
            ext_id = _find(payload, "shipment_id", "shipmentid")
            if ext_id:
                sb = await get_async_admin_supabase()
                res = await sb.table("shipping_shipments").select("*").eq("provider_key", provider_key).eq("external_shipment_id", str(ext_id)).maybe_single().execute()
                row = res.data if res else None
        if not row:
            raise HTTPException(status_code=404, detail="Shipment could not be matched to provider event.")

        provider_status = _provider_status(payload) or str(row.get("provider_status") or "unknown")
        event_id = str(_find(payload, "event_id", "tracking_event_id", "shipment_event_id", "id") or "").strip()
        if not event_id:
            canonical = json.dumps({"shipment": row["id"], "status": provider_status, "payload": payload}, sort_keys=True, default=str)
            event_id = hashlib.sha256(canonical.encode()).hexdigest()
        fresh = await self.repo.record_event(str(row["id"]), event_id, provider_status, payload)
        if not fresh:
            return row

        now = _now()
        updates: dict[str, Any] = {
            "provider_status": provider_status, "last_provider_event_at": now,
            "status": provider_status or row.get("status"), "metadata": {**(row.get("metadata") or {}), "last_provider_event": payload},
            "updated_at": now,
        }
        if awb: updates["tracking_number"] = awb
        tracking_url = _find(payload, "tracking_url", "track_url")
        if tracking_url: updates["tracking_url"] = str(tracking_url)
        courier = _find(payload, "courier_name", "courier")
        if courier: updates["courier_name"] = str(courier)
        if provider_status in _SHIPPED_PROVIDER_STATUSES and not row.get("shipped_at"):
            updates["shipped_at"] = now
        if provider_status in _DELIVERED_PROVIDER_STATUSES and not row.get("delivered_at"):
            updates["delivered_at"] = now
        updated = await self.repo.update(str(row["id"]), updates)

        sb = await get_async_admin_supabase()
        order_res = await sb.table("orders").select("id,order_number,status,customer_id,shipping_email").eq("id", row["order_id"]).maybe_single().execute()
        order = order_res.data if order_res else None
        if not order:
            return updated

        current = str(order.get("status") or "").lower()
        if provider_status in _DELIVERED_PROVIDER_STATUSES and current != "delivered":
            await sb.table("orders").update({"status": "delivered", "delivered_at": now, "updated_at": now, "tracking_number": awb or row.get("tracking_number")}).eq("id", row["order_id"]).execute()
            await get_event_bus().publish_durable(OrderStatusChangedEvent(order={**order, "status": "delivered"}, customer_id=order.get("customer_id"), old_status=current, new_status="delivered"))
        elif provider_status in _SHIPPED_PROVIDER_STATUSES and current in {"paid", "processing"}:
            await sb.table("orders").update({"status": "shipped", "shipped_at": now, "fulfilled_at": now, "tracking_number": awb or row.get("tracking_number"), "updated_at": now}).eq("id", row["order_id"]).execute()
            email = str(order.get("shipping_email") or "").strip()
            await get_event_bus().publish_durable(OrderShippedEvent(order={**order, "status": "shipped", "tracking_number": awb}, customer_email=email, customer_id=order.get("customer_id"), tracking_number=awb or None))

        uid = order.get("customer_id")
        if uid and provider_status in {"out_for_delivery", "out_for_delivery_today"}:
            try:
                await send_push_to_user(uid, title="Your order is out for delivery", body=f"Order #{order.get('order_number')} is out for delivery.", icon="/icons/ri-truck.png", url="/orders")
            except Exception:
                logger.exception("Failed to send out-for-delivery push")

        return updated

    async def handle_webhook(self, provider_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.apply_provider_event(provider_key, payload)

    async def cancel(self, shipment_id: str) -> dict[str, Any]:
        row = await self._get_provider_row(shipment_id)
        try: response = await get_shipping_provider(row["provider_key"]).cancel_shipment(str(row["external_shipment_id"]))
        except Exception as exc: raise HTTPException(status_code=502, detail="Unable to cancel provider shipment.") from exc
        return await self.repo.update(shipment_id, {"status": "cancelled", "provider_status": "cancelled", "metadata": {**(row.get("metadata") or {}), "cancel": response}, "updated_at": _now()})
