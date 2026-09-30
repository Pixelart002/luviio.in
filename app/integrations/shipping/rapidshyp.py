"""RapidShyp API adapter.

RapidShyp uses a single API-key header (rapidshyp-token). The adapter keeps
provider-specific payload/response mapping here so checkout and fulfillment
orchestration remain provider-neutral.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.integrations.shipping.base import ShippingProvider

logger = logging.getLogger(__name__)


class RapidShypProvider(ShippingProvider):
    key = "rapidshyp"
    supports_label = True
    supports_manifest = False
    supports_invoice = False
    default_base_url = "https://api.rapidshyp.com/rapidshyp/apis/v1"

    def __init__(self) -> None:
        self.base_url = os.getenv("RAPIDSHYP_BASE_URL", self.default_base_url).strip().rstrip("/")
        self.token = os.getenv("RAPIDSHYP_TOKEN", "").strip()
        self.timeout = httpx.Timeout(
            float(os.getenv("RAPIDSHYP_TIMEOUT_SECONDS", "6")),
            connect=float(os.getenv("RAPIDSHYP_CONNECT_TIMEOUT_SECONDS", "2")),
            read=float(os.getenv("RAPIDSHYP_READ_TIMEOUT_SECONDS", "6")),
            write=float(os.getenv("RAPIDSHYP_WRITE_TIMEOUT_SECONDS", "6")),
            pool=float(os.getenv("RAPIDSHYP_POOL_TIMEOUT_SECONDS", "1")),
        )

    def _configured(self) -> None:
        if not self.token:
            raise RuntimeError("RapidShyp provider is not configured.")

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        self._configured()
        headers = {
            "rapidshyp-token": self.token,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    json=json,
                )
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
            logger.warning(
                "[RAPIDSHYP] provider connection failed | host=%s method=%s path=%s error_type=%s",
                self.base_url,
                method,
                path,
                type(exc).__name__,
            )
            raise RuntimeError(f"RapidShyp request failed ({type(exc).__name__}).") from exc

        if response.is_error:
            logger.error(
                "[RAPIDSHYP] API request failed | status=%s method=%s path=%s body=%s",
                response.status_code,
                method,
                path,
                response.text[:1000].replace("\n", " "),
            )
            response.raise_for_status()

        data = response.json()
        return data if isinstance(data, dict) else {"data": data}

    async def serviceability(
        self,
        *,
        pickup_postcode: str,
        delivery_postcode: str,
        weight_kg: float,
        cod: bool,
        declared_value: float | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/serviceability_check",
            json={
                "Pickup_pincode": pickup_postcode,
                "Delivery_pincode": delivery_postcode,
                "cod": bool(cod),
                "total_order_value": float(declared_value or 0),
                "weight": float(weight_kg),
            },
        )

    async def create_shipment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Translate Luviio's existing normalized shipment payload to RapidShyp."""
        billing_same = bool(payload.get("shipping_is_billing", True))

        def _name(first_key: str, last_key: str) -> tuple[str, str]:
            first = str(payload.get(first_key) or "").strip() or "Customer"
            last = str(payload.get(last_key) or "").strip()
            return first, last

        billing_first, billing_last = _name("billing_customer_name", "billing_last_name")
        shipping_first, shipping_last = _name("shipping_customer_name", "shipping_last_name")
        if billing_same:
            shipping_first, shipping_last = billing_first, billing_last

        items = []
        for item in payload.get("order_items") or []:
            if not isinstance(item, dict):
                continue
            units = max(int(item.get("units") or 1), 1)
            items.append(
                {
                    "itemName": str(item.get("name") or "Product"),
                    "sku": str(item.get("sku") or ""),
                    "description": str(item.get("name") or "Product"),
                    "units": units,
                    "unitPrice": float(item.get("selling_price") or 0),
                    "tax": float(item.get("tax") or 0),
                    "hsn": str(item.get("hsn") or ""),
                    "productLength": float(payload.get("length") or 10),
                    "productBreadth": float(payload.get("breadth") or 10),
                    "productHeight": float(payload.get("height") or 10),
                    "productWeight": max(float(payload.get("weight") or 0.5) * 1000 / units, 1.0),
                    "brand": "Luviio",
                    "isFragile": False,
                    "isPersonalisable": False,
                    "pickupAddressName": str(payload.get("pickup_location") or ""),
                }
            )
        if not items:
            raise ValueError("RapidShyp order requires at least one order item.")

        pickup = {
            "contactName": str(payload.get("pickup_contact_name") or "Luviio"),
            "pickupName": str(payload.get("pickup_location") or "Luviio"),
            "pickupEmail": str(payload.get("pickup_email") or ""),
            "pickupPhone": str(payload.get("pickup_phone") or ""),
            "pickupAddress1": str(payload.get("pickup_address") or ""),
            "pickupAddress2": str(payload.get("pickup_address_2") or ""),
            "pinCode": str(payload.get("pickup_pincode") or ""),
        }
        # The provider API allows a pickup location to be created on order
        # creation. Luviio's seller Business Profile remains the source of truth.

        shipping = {
            "firstName": shipping_first,
            "lastName": shipping_last,
            "addressLine1": str(payload.get("shipping_address") or payload.get("billing_address") or ""),
            "addressLine2": str(payload.get("shipping_address_2") or payload.get("billing_address_2") or ""),
            "pinCode": str(payload.get("shipping_pincode") or payload.get("billing_pincode") or ""),
            "email": str(payload.get("shipping_email") or payload.get("billing_email") or ""),
            "phone": str(payload.get("shipping_phone") or payload.get("billing_phone") or ""),
        }
        billing = {
            "firstName": billing_first,
            "lastName": billing_last,
            "addressLine1": str(payload.get("billing_address") or ""),
            "addressLine2": str(payload.get("billing_address_2") or ""),
            "pinCode": str(payload.get("billing_pincode") or ""),
            "email": str(payload.get("billing_email") or ""),
            "phone": str(payload.get("billing_phone") or ""),
        }

        return await self._request(
            "POST",
            "/create_order",
            json={
                "orderId": str(payload.get("order_id") or ""),
                "orderDate": str(payload.get("order_date") or "")[:10],
                "pickupAddressName": str(payload.get("pickup_location") or ""),
                "pickupLocation": pickup,
                "storeName": "DEFAULT",
                "billingIsShipping": billing_same,
                "shippingAddress": shipping,
                "billingAddress": billing,
                "orderItems": items,
                "paymentMethod": "COD" if str(payload.get("payment_method") or "").upper() == "COD" else "PREPAID",
                "shippingCharges": float(payload.get("shipping_charges") or 0),
                "giftWrapCharges": float(payload.get("giftwrap_charges") or 0),
                "transactionCharges": float(payload.get("transaction_charges") or 0),
                "totalDiscount": float(payload.get("total_discount") or 0),
                "codCharges": 0,
                "prepaidAmount": float(payload.get("sub_total") or 0)
                if str(payload.get("payment_method") or "").upper() != "COD"
                else 0,
                "packageDetails": {
                    "packageLength": float(payload.get("length") or 10),
                    "packageBreadth": float(payload.get("breadth") or 10),
                    "packageHeight": float(payload.get("height") or 10),
                    "packageWeight": max(float(payload.get("weight") or 0.5) * 1000, 1.0),
                },
            },
        )

    async def assign_awb(self, *, shipment_id: str, courier_id: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"shipment_id": str(shipment_id)}
        if courier_id is not None:
            body["courier_code"] = str(courier_id)
        return await self._request("POST", "/assign_awb", json=body)

    async def generate_pickup(self, *, shipment_id: str, tracking_number: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"shipment_id": str(shipment_id)}
        if tracking_number:
            body["awb"] = str(tracking_number)
        return await self._request("POST", "/schedule_pickup", json=body)

    async def generate_label(self, *, shipment_id: str) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/b2b/orders/get_tracking_info",
            json={"shipmentID": str(shipment_id)},
        )
        label_url = _find(response, "master_label_url", "mps_label_url", "label_url")
        if not label_url:
            raise RuntimeError("RapidShyp tracking response did not include a label URL.")
        return {"label_url": str(label_url), "provider_response": response}

    async def generate_manifest(self, *, shipment_id: str) -> dict[str, Any]:
        raise RuntimeError("RapidShyp manifest API is not part of the documented integration used by Luviio.")

    async def print_invoice(self, *, order_id: str) -> dict[str, Any]:
        raise RuntimeError("RapidShyp courier-invoice API is not part of the documented integration used by Luviio.")

    async def track(self, tracking_number: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/b2b/orders/get_tracking_info",
            json={"awb": str(tracking_number)},
        )

    async def cancel_shipment(
        self,
        *,
        shipment_id: str,
        tracking_number: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError("RapidShyp cancellation endpoint requires account-specific verification before activation.")


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
