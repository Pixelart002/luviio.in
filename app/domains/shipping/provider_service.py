"""Shipping provider orchestration for admin fulfillment."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.supabase import get_async_admin_supabase
from app.integrations.shipping.registry import get_shipping_provider
from app.domains.shipping.provider_repository import ShippingProviderRepository


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
    ) -> dict[str, Any]:
        try:
            provider = get_shipping_provider(provider_key)
            return await provider.serviceability(
                pickup_postcode=pickup_postcode,
                delivery_postcode=delivery_postcode,
                weight_kg=weight_kg,
                cod=cod,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Shipping provider unavailable: {provider_key}.",
            ) from exc

    async def create_for_order(
        self,
        order_id: str,
        provider_key: str,
        pickup_location: str,
        weight_kg: float,
        length_cm: float,
        breadth_cm: float,
        height_cm: float,
    ) -> dict[str, Any]:
        existing = await self.repo.get_by_order(order_id, provider_key)
        if existing:
            return existing

        sb = await get_async_admin_supabase()
        order_res = await (
            sb.table("orders")
            .select("*, order_items(*, products(name, sku, hsn_code))")
            .eq("id", order_id)
            .maybe_single()
            .execute()
        )
        order = order_res.data if order_res else None
        if not order:
            raise HTTPException(status_code=404, detail="Order not found.")

        items = order.get("order_items") or []
        payment_method = str(order.get("payment_method") or "").upper()
        provider_items = [
            {
                "name": item.get("product_name") or (item.get("products") or {}).get("name") or "Product",
                "sku": item.get("sku") or (item.get("products") or {}).get("sku") or str(item.get("product_id")),
                "units": int(item.get("quantity") or 1),
                "selling_price": float(item.get("unit_price") or 0),
                "discount": float(item.get("discount_amount") or 0),
                "tax": float(item.get("tax_amount") or 0),
                "hsn": str(item.get("hsn_code") or (item.get("products") or {}).get("hsn_code") or ""),
            }
            for item in items
        ]
        shipping = {
            "name": order.get("shipping_name") or "",
            "phone": order.get("shipping_phone") or "",
            "email": order.get("shipping_email") or "",
            "address": order.get("shipping_line1") or "",
            "address_2": order.get("shipping_line2") or "",
            "city": order.get("shipping_city") or "",
            "state": order.get("shipping_state") or "",
            "country": order.get("shipping_country") or "India",
            "pincode": order.get("shipping_postal_code") or "",
        }
        first, *last = (shipping["name"] or "Customer").split()
        payload = {
            "order_id": order.get("order_number") or str(order_id),
            "order_date": order.get("created_at"),
            "pickup_location": pickup_location,
            "billing_customer_name": first,
            "billing_last_name": " ".join(last),
            "billing_address": shipping["address"],
            "billing_address_2": shipping["address_2"],
            "billing_city": shipping["city"],
            "billing_pincode": shipping["pincode"],
            "billing_state": shipping["state"],
            "billing_country": shipping["country"],
            "billing_email": shipping["email"],
            "billing_phone": shipping["phone"],
            "shipping_is_billing": True,
            "shipping_customer_name": first,
            "shipping_last_name": " ".join(last),
            "shipping_address": shipping["address"],
            "shipping_address_2": shipping["address_2"],
            "shipping_city": shipping["city"],
            "shipping_pincode": shipping["pincode"],
            "shipping_state": shipping["state"],
            "shipping_country": shipping["country"],
            "shipping_email": shipping["email"],
            "shipping_phone": shipping["phone"],
            "order_items": provider_items,
            "payment_method": "COD" if payment_method == "COD" else "Prepaid",
            "sub_total": float(order.get("subtotal") or 0),
            "length": length_cm,
            "breadth": breadth_cm,
            "height": height_cm,
            "weight": weight_kg,
        }
        try:
            response = await get_shipping_provider(provider_key).create_shipment(payload)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Unable to create shipment with provider.") from exc

        data = response.get("shipment_id") or response.get("shipment") or {}
        if isinstance(data, dict):
            external_shipment_id = data.get("id") or data.get("shipment_id")
        else:
            external_shipment_id = data
        external_order_id = response.get("order_id")
        return await self.repo.create(
            {
                "order_id": order_id,
                "provider_key": provider_key,
                "external_order_id": str(external_order_id) if external_order_id else None,
                "external_shipment_id": str(external_shipment_id) if external_shipment_id else None,
                "status": "created",
                "metadata": response,
            }
        )

    async def track(self, provider_key: str, tracking_number: str) -> dict[str, Any]:
        try:
            return await get_shipping_provider(provider_key).track(tracking_number)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Unable to fetch shipment tracking.") from exc
