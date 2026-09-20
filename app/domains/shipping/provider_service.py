"""End-to-end shipment orchestration: order -> courier -> AWB -> pickup -> tracking."""
from __future__ import annotations
import hashlib, json, logging, os
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

    async def serviceability(self, provider_key: str, pickup_postcode: str, delivery_postcode: str, weight_kg: float, cod: bool, declared_value: float | None = None) -> dict[str, Any]:
        try:
            return await get_shipping_provider(provider_key).serviceability(
                pickup_postcode=pickup_postcode, delivery_postcode=delivery_postcode,
                weight_kg=weight_kg, cod=cod, declared_value=declared_value,
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Shipping provider unavailable: {provider_key}.") from exc

    async def quote_for_checkout(self, delivery_postcode: str, weight_kg: float, cod: bool, declared_value: float | None = None) -> dict[str, Any]:
        """Return live Shiprocket courier rates for checkout; never use the store flat-rate setting."""
        import os

        # Business Profile is the seller SSOT. Shiprocket pickup postcode must
        # come from the configured seller/business profile, not a duplicate env value.
        sb = await get_async_admin_supabase()
        profile_rows = await sb.table("system_settings").select("key,value").in_(
            "key",
            ["seller_pincode", "business_brand_name", "business_legal_name"],
        ).execute()
        profile = {
            str(row.get("key")): row.get("value")
            for row in (profile_rows.data or [])
            if isinstance(row, dict)
        }
        def _setting_text(key: str) -> str:
            value = profile.get(key)
            return value.strip() if isinstance(value, str) else str(value or "").strip()

        pickup_postcode = _setting_text("seller_pincode")
        if not pickup_postcode:
            raise HTTPException(status_code=503, detail="Business Profile seller PIN code is not configured.")
        if not pickup_postcode.isdigit() or len(pickup_postcode) != 6:
            raise HTTPException(status_code=503, detail="Business Profile seller PIN code is invalid.")
        delivery_postcode = str(delivery_postcode or "").strip()
        if not delivery_postcode.isdigit() or len(delivery_postcode) != 6:
            raise HTTPException(status_code=422, detail="A valid 6-digit delivery PIN code is required.")
        try:
            weight = float(weight_kg)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Shipment weight is invalid.")
        if weight <= 0:
            raise HTTPException(status_code=422, detail="Shipment weight must be greater than zero.")

        try:
            response = await get_shipping_provider("shiprocket").serviceability(
                pickup_postcode=pickup_postcode,
                delivery_postcode=delivery_postcode,
                weight_kg=weight,
                cod=cod,
                declared_value=declared_value,
            )
        except Exception as exc:
            logger.error("[SHIPROCKET] Serviceability failed", exc_info=True)
            raise HTTPException(status_code=502, detail="Shiprocket could not calculate shipping for this address.") from exc

        data = response.get("data") if isinstance(response, dict) else None
        couriers = data.get("available_courier_companies", []) if isinstance(data, dict) else data
        if not isinstance(couriers, list) or not couriers:
            raise HTTPException(status_code=422, detail="No Shiprocket courier is serviceable for this address.")

        quotes = []
        for courier in couriers:
            if not isinstance(courier, dict) or courier.get("blocked"):
                continue
            raw_rate = courier.get("rate")
            if isinstance(raw_rate, dict):
                raw_rate = raw_rate.get("rate") or raw_rate.get("total")
            try:
                rate = float(raw_rate)
            except (TypeError, ValueError):
                rate = 0.0
            if rate <= 0:
                try:
                    rate = float(courier.get("freight_charge") or 0) + float(courier.get("cod_charges") or 0) + float(courier.get("other_charges") or 0)
                except (TypeError, ValueError):
                    rate = 0.0
            if rate <= 0:
                continue
            try:
                discount = float(courier.get("discount") or 0)
            except (TypeError, ValueError):
                discount = 0.0
            quotes.append({
                "courier_id": courier.get("courier_company_id") or courier.get("id"),
                "courier_name": courier.get("courier_name") or "Shiprocket courier",
                "shipping_cost": round(rate, 2),
                "discount": round(discount, 2),
                "freight_charge": float(courier.get("freight_charge") or rate),
                "cod_charge": float(courier.get("cod_charges") or 0),
                "other_charges": float(courier.get("other_charges") or 0),
                "chargeable_weight_kg": courier.get("charge_weight"),
                "estimated_delivery_days": courier.get("estimated_delivery_days"),
                "etd_hours": courier.get("etd_hours"),
                "etd": courier.get("etd"),
                "rating": courier.get("rating"),
            })
        if not quotes:
            raise HTTPException(status_code=422, detail="Shiprocket returned no usable courier rate.")
        # Checkout uses the fastest serviceable courier, not the cheapest legacy/store rate.
        # Shiprocket serviceability returns both shipment rate and delivery-time fields.
        # Never hardcode a courier charge: the selected shipping_cost always comes from
        # the current Shiprocket response.
        def _etd_hours(quote: dict[str, Any]) -> float:
            raw = quote.get("etd_hours")
            try:
                value = float(raw)
                return value if value >= 0 else float("inf")
            except (TypeError, ValueError):
                return float("inf")

        def _etd_days(quote: dict[str, Any]) -> float:
            raw = str(quote.get("estimated_delivery_days") or "").strip()
            try:
                # Handles normal integer/string values such as "3".
                return float(raw)
            except (TypeError, ValueError):
                return float("inf")

        quotes.sort(
            key=lambda q: (
                _etd_hours(q),
                _etd_days(q),
                q["shipping_cost"],
                str(q["courier_name"]),
            )
        )
        selected = quotes[0]

        # Safe rate diagnostics: no credentials/tokens or customer address details.
        provider = get_shipping_provider("shiprocket")
        logger.info(
            "[SHIPROCKET] Checkout quote selected | env=%s delivery=%s weight_kg=%.3f cod=%s courier=%s courier_id=%s rate=%.2f freight=%.2f cod_charge=%.2f other=%.2f discount=%.2f",
            getattr(provider, "environment", "unknown"),
            delivery_postcode,
            weight,
            cod,
            selected.get("courier_name"),
            selected.get("courier_id"),
            float(selected.get("shipping_cost") or 0),
            float(selected.get("freight_charge") or 0),
            float(selected.get("cod_charge") or 0),
            float(selected.get("other_charges") or 0),
            float(selected.get("discount") or 0),
        )
        return {
            "provider": "shiprocket",
            "pickup_postcode": pickup_postcode,
            "delivery_postcode": delivery_postcode,
            "weight_kg": weight,
            "cod": cod,
            "declared_value": declared_value,
            "selected": selected,
            "selection": "fastest_available",
            "quotes": quotes,
            "couriers": quotes,
        }

    async def create_for_order(self, order_id: str, provider_key: str, pickup_location: str | None = None, weight_kg: float | None = None, length_cm: float | None = None, breadth_cm: float | None = None, height_cm: float | None = None) -> dict[str, Any]:
        existing = await self.repo.get_by_order(order_id, provider_key)
        if existing:
            return existing
        sb = await get_async_admin_supabase()
        res = await (sb.table("orders").select("*, order_items(*, products(name, sku, hsn_code, weight, weight_unit))").eq("id", order_id).maybe_single().execute())
        order = res.data if res else None
        if not order:
            raise HTTPException(status_code=404, detail="Order not found.")
        order_status = str(order.get("status") or "").lower()
        payment_method = str(order.get("payment_method") or "").lower()
        if order_status in {"cancelled", "refunded"}:
            raise HTTPException(status_code=409, detail="Cancelled/refunded orders cannot be shipped.")
        if payment_method not in {"cod", "cash_on_delivery"} and order_status not in {"paid", "processing", "shipped"}:
            raise HTTPException(status_code=409, detail="Online orders must be paid before courier booking.")

        items = order.get("order_items") or []
        payment_method = str(order.get("payment_method") or "").upper()

        # All shipment inputs are order-driven where possible. Do not make the
        # fulfillment operator re-enter values that already exist on the order.
        # Shiprocket requires weight/dimensions; weight is calculated from the
        # product snapshots and dimensions fall back to configured parcel defaults.
        if weight_kg is None or float(weight_kg) <= 0:
            from decimal import Decimal
            total_weight = Decimal("0")
            for item in items:
                product = item.get("products") or {}
                raw_weight = product.get("weight")
                if raw_weight in (None, ""):
                    continue
                try:
                    item_weight = Decimal(str(raw_weight))
                    if str(product.get("weight_unit") or "g").lower() == "g":
                        item_weight /= Decimal("1000")
                    total_weight += item_weight * int(item.get("quantity") or 0)
                except (ArithmeticError, TypeError, ValueError):
                    continue
            if total_weight > 0:
                weight_kg = float(total_weight)
            else:
                try:
                    weight_kg = float(os.getenv("SHIPROCKET_RATE_DEFAULT_WEIGHT_KG", "0.5"))
                except (TypeError, ValueError):
                    weight_kg = 0.5

        def _parcel_dimension(name: str) -> float:
            try:
                value = float(os.getenv(name, "10"))
                return value if value > 0 else 10.0
            except (TypeError, ValueError):
                return 10.0

        length_cm = float(length_cm) if length_cm and float(length_cm) > 0 else _parcel_dimension("SHIPROCKET_DEFAULT_LENGTH_CM")
        breadth_cm = float(breadth_cm) if breadth_cm and float(breadth_cm) > 0 else _parcel_dimension("SHIPROCKET_DEFAULT_BREADTH_CM")
        height_cm = float(height_cm) if height_cm and float(height_cm) > 0 else _parcel_dimension("SHIPROCKET_DEFAULT_HEIGHT_CM")
        # Shiprocket custom orders must use an existing seller pickup location.
        # Resolve the configured name against Shiprocket itself so we never send a
        # stale/typo pickup name and then receive its generic address error.
        # Business Profile is the seller identity SSOT. An explicit argument is
        # still allowed for an already-registered Shiprocket pickup name; otherwise
        # prefer the profile brand/legal name and verify it against Shiprocket.
        profile_rows = await sb.table("system_settings").select("key,value").in_(
            "key",
            [\n                "business_brand_name", "business_legal_name", "business_email",\n                "business_phone", "seller_address_line1", "seller_address_line2",\n                "seller_city", "seller_state", "seller_country", "seller_pincode",\n            ],
        ).execute()
        profile = {
            str(row.get("key")): row.get("value")
            for row in (profile_rows.data or [])
            if isinstance(row, dict)
        }
        def _profile_text(key: str) -> str:
            value = profile.get(key)
            return value.strip() if isinstance(value, str) else str(value or "").strip()

        profile_pickup_name = _profile_text("business_brand_name") or _profile_text("business_legal_name")
        pickup_location = (pickup_location or profile_pickup_name).strip()
        if provider_key == "shiprocket":
            provider = get_shipping_provider("shiprocket")
            try:
                pickup_locations = await provider.list_pickup_locations()
            except Exception as exc:
                logger.error(
                    "[SHIPROCKET] Could not read pickup locations | env=%s",
                    getattr(provider, "environment", "unknown"),
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Shiprocket pickup locations could not be verified.",
                ) from exc

            def _pickup_status_active(item: dict[str, Any]) -> bool:
                # Shiprocket examples use numeric status=2 for an active pickup.
                # Keep compatibility with boolean/string variants returned by
                # older/provider-specific responses, but reject explicit inactive states.
                raw = item.get("status")
                if isinstance(raw, bool):
                    return raw
                normalized = str(raw if raw is not None else "2").strip().lower()
                return normalized not in {"0", "false", "inactive", "disabled", "deactivated"}

            usable_locations = [
                item for item in pickup_locations
                if str(item.get("pickup_location") or "").strip()
                and _pickup_status_active(item)
            ]

            logger.info(
                "[SHIPROCKET] Pickup locations resolved | env=%s total=%d usable=%d names=%s statuses=%s",
                getattr(provider, "environment", "unknown"),
                len(pickup_locations),
                len(usable_locations),
                [
                    str(item.get("pickup_location") or "").strip()
                    for item in pickup_locations[:10]
                ],
                [
                    str(item.get("status") if item.get("status") is not None else "missing")
                    for item in pickup_locations[:10]
                ],
            )

            if not pickup_locations:
                # The Shiprocket custom-order API requires an existing pickup
                # location. If the authenticated account has none, register the
                # seller's configured Business Profile address through the same
                # Shiprocket API account/environment, then re-read the locations.
                # This removes the stale/manual "Home" dependency while keeping
                # Business Profile as Luviio's seller source of truth.
                pickup_name = (
                    str(os.getenv("SHIPROCKET_PICKUP_LOCATION") or "").strip()
                    or profile_pickup_name
                    or "Luviio"
                )
                pickup_email = _profile_text("business_email") or str(
                    os.getenv("SHIPROCKET_EMAIL") or ""
                ).strip()
                pickup_phone = "".join(
                    ch for ch in _profile_text("business_phone") if ch.isdigit()
                )
                pickup_address = _profile_text("seller_address_line1")
                pickup_address_2 = _profile_text("seller_address_line2")
                pickup_city = _profile_text("seller_city")
                pickup_state = _profile_text("seller_state")
                pickup_country = _profile_text("seller_country") or "India"
                pickup_pin = _profile_text("seller_pincode")

                if len(pickup_phone) != 10:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Shiprocket has no pickup location. Configure a valid "
                            "Business Profile phone number before automatic pickup registration."
                        ),
                    )
                if not pickup_address or not pickup_city or not pickup_state or not pickup_pin:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Shiprocket has no pickup location. Complete the Business Profile "
                            "seller address, city, state and 6-digit PIN code first."
                        ),
                    )
                if not pickup_pin.isdigit() or len(pickup_pin) != 6:
                    raise HTTPException(
                        status_code=503,
                        detail="Business Profile seller PIN code must contain exactly 6 digits.",
                    )

                try:
                    await provider.add_pickup_location(
                        {
                            "pickup_location": pickup_name[:36],
                            "name": _profile_text("business_legal_name") or pickup_name[:80],
                            "email": pickup_email,
                            "phone": pickup_phone,
                            "address": pickup_address[:80],
                            "address_2": pickup_address_2[:80],
                            "city": pickup_city,
                            "state": pickup_state,
                            "country": pickup_country,
                            "pin_code": pickup_pin,
                        }
                    )
                    pickup_locations = await provider.list_pickup_locations()
                    logger.info(
                        "[SHIPROCKET] Pickup location auto-registration attempted | env=%s name=%s total_after=%d",
                        getattr(provider, "environment", "unknown"),
                        pickup_name[:36],
                        len(pickup_locations),
                    )
                except Exception as exc:
                    logger.error(
                        "[SHIPROCKET] Pickup auto-registration failed | env=%s name=%s",
                        getattr(provider, "environment", "unknown"),
                        pickup_name[:36],
                        exc_info=True,
                    )
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Shiprocket has no pickup location and automatic registration "
                            "failed. Check the Shiprocket API account/environment and Business Profile."
                        ),
                    ) from exc

                if not pickup_locations:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Shiprocket pickup registration was accepted but the location "
                            "is not yet visible to the API. Verify/activate it in Shiprocket "
                            "and retry."
                        ),
                    )
            if not usable_locations:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Shiprocket pickup locations exist, but none is active. "
                        "Activate a verified pickup address in Shiprocket."
                    ),
                )

            if pickup_location:
                requested = pickup_location.casefold()
                matched = next(
                    (
                        item for item in usable_locations
                        if str(item.get("pickup_location") or "").strip().casefold() == requested
                    ),
                    None,
                )
                if matched is None:
                    available = ", ".join(
                        str(item.get("pickup_location")).strip()
                        for item in usable_locations[:10]
                    )
                    raise HTTPException(
                        status_code=503,
                        detail=f"Configured Shiprocket pickup location was not found in the account. Available: {available}",
                    )
                # Use Shiprocket's canonical spelling/casing.
                pickup_location = str(matched["pickup_location"]).strip()
            else:
                # If no env override is supplied, use the account's primary
                # pickup location. Shiprocket exposes is_primary_location on
                # the pickup-location resource.
                primary = next(
                    (item for item in usable_locations if item.get("is_primary_location") in (1, True, "1", "true")),
                    usable_locations[0],
                )
                pickup_location = str(primary["pickup_location"]).strip()
                logger.info(
                    "[SHIPROCKET] Auto-selected primary pickup location | env=%s configured=%s",
                    getattr(provider, "environment", "unknown"),
                    bool(os.getenv("SHIPROCKET_PICKUP_LOCATION")),
                )
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
        billing_same_as_shipping = order.get("billing_same_as_shipping")
        if billing_same_as_shipping is None:
            billing_same_as_shipping = True
        if billing_same_as_shipping:
            billing = dict(shipping)
        else:
            billing = {
                "name": order.get("billing_name") or "",
                "phone": order.get("billing_phone") or "",
                "email": order.get("billing_email") or "",
                "address": order.get("billing_line1") or "",
                "address_2": order.get("billing_line2") or "",
                "city": order.get("billing_city") or "",
                "state": order.get("billing_state") or "",
                "country": order.get("billing_country") or "India",
                "pincode": order.get("billing_postal_code") or "",
            }

        if not shipping["name"] or not shipping["address"] or not shipping["city"] or not shipping["state"] or not shipping["pincode"]:
            raise HTTPException(status_code=422, detail="Order shipping address is incomplete.")
        if not billing["name"] or not billing["address"] or not billing["city"] or not billing["state"] or not billing["pincode"]:
            raise HTTPException(status_code=422, detail="Order billing address is incomplete.")

        # Shiprocket expects an Indian customer phone number; do not send an
        # invalid 11-digit value and rely on its opaque 400 response.
        for label, address in (("shipping", shipping), ("billing", billing)):
            phone = "".join(ch for ch in str(address.get("phone") or "") if ch.isdigit())
            if len(phone) != 10:
                raise HTTPException(status_code=422, detail=f"Order {label} phone number must contain exactly 10 digits.")
            address["phone"] = phone

        shipping_first, *shipping_last = (shipping["name"] or "Customer").split()
        billing_first, *billing_last = (billing["name"] or "Customer").split()

        # Shiprocket's custom-order contract treats shipping fields as
        # conditional when shipping_is_billing=true. Keep the payload aligned
        # with that contract instead of duplicating the shipping address.
        # Shiprocket's public examples include the shipping keys even when
        # shipping_is_billing=true. Keep those keys present with empty values;
        # omitting them can trigger the generic "Please add billing/shipping
        # address first" response on some sandbox accounts.
        shipping_payload = {
            "shipping_customer_name": "",
            "shipping_last_name": "",
            "shipping_address": "",
            "shipping_address_2": "",
            "shipping_city": "",
            "shipping_pincode": "",
            "shipping_state": "",
            "shipping_country": "",
            "shipping_email": "",
            "shipping_phone": "",
        } if billing_same_as_shipping else {
            "shipping_customer_name": shipping_first,
            "shipping_last_name": " ".join(shipping_last),
            "shipping_address": shipping["address"],
            "shipping_address_2": shipping["address_2"],
            "shipping_city": shipping["city"],
            "shipping_pincode": shipping["pincode"],
            "shipping_state": shipping["state"],
            "shipping_country": shipping["country"],
            "shipping_email": shipping["email"],
            "shipping_phone": shipping["phone"],
        }
        raw_order_date = order.get("created_at")
        order_date = raw_order_date
        if raw_order_date:
            try:
                order_date = datetime.fromisoformat(str(raw_order_date).replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError):
                order_date = str(raw_order_date)

        payload = {
            "order_id": order.get("order_number") or str(order_id),
            "order_date": order_date,
            "pickup_location": pickup_location,
            "billing_customer_name": billing_first, "billing_last_name": " ".join(billing_last),
            "billing_address": billing["address"], "billing_address_2": billing["address_2"],
            "billing_city": billing["city"], "billing_pincode": billing["pincode"], "billing_state": billing["state"],
            "billing_country": "India" if str(billing["country"]).upper() in {"IN", "IND"} else billing["country"],
            "billing_email": billing["email"], "billing_phone": billing["phone"],
            "shipping_is_billing": bool(billing_same_as_shipping),
            **shipping_payload,
            "order_items": provider_items, "payment_method": "COD" if payment_method == "COD" else "Prepaid",
            "shipping_charges": float(order.get("shipping_cost") or 0),
            "giftwrap_charges": 0,
            "transaction_charges": 0,
            "total_discount": float(order.get("discount_amount") or 0),
            "sub_total": max(float(order.get("subtotal") or 0) - float(order.get("discount_amount") or 0), 0),
            "length": length_cm, "breadth": breadth_cm,
            "height": height_cm, "weight": weight_kg,
        }
        try:
            response = await get_shipping_provider(provider_key).create_shipment(payload)
        except Exception as exc:
            logger.error(
                "[SHIPROCKET] Shipment creation failed | provider=%s order_id=%s order_number=%s shipping_charges=%.2f weight_kg=%.3f",
                provider_key,
                order_id,
                order.get("order_number"),
                float(order.get("shipping_cost") or 0),
                float(weight_kg),
                exc_info=True,
            )
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
        tracking_url = _find(response, "tracking_url", "track_url")
        if not awb:
            raise HTTPException(status_code=502, detail="Courier provider returned no AWB.")
        updated = await self.repo.update(shipment_id, {
            "tracking_number": str(awb), "courier_name": str(courier) if courier else row.get("courier_name"), "tracking_url": str(tracking_url) if tracking_url else row.get("tracking_url"),
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

        if uid and provider_status in {"ndr", "ndr_action_required", "delivery_attempt_failed"}:
            try:
                await send_push_to_user(
                    uid,
                    title="Delivery needs your attention",
                    body=f"Courier reported a delivery issue for order #{order.get('order_number')}.",
                    icon="/icons/ri-alert.png",
                    url=f"/orders/{order.get('order_number')}",
                )
            except Exception:
                logger.exception("Failed to send NDR push")
        if uid and provider_status in {"rto", "rto_initiated", "rto_delivered"}:
            try:
                await send_push_to_user(
                    uid,
                    title="Delivery exception update",
                    body=f"Courier reported an RTO update for order #{order.get('order_number')}.",
                    icon="/icons/ri-arrow-go-back-line.png",
                    url=f"/orders/{order.get('order_number')}",
                )
            except Exception:
                logger.exception("Failed to send RTO push")

        return updated

    async def handle_webhook(self, provider_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.apply_provider_event(provider_key, payload)

    async def cancel(self, shipment_id: str) -> dict[str, Any]:
        row = await self._get_provider_row(shipment_id)
        try: response = await get_shipping_provider(row["provider_key"]).cancel_shipment(str(row["external_shipment_id"]))
        except Exception as exc: raise HTTPException(status_code=502, detail="Unable to cancel provider shipment.") from exc
        return await self.repo.update(shipment_id, {"status": "cancelled", "provider_status": "cancelled", "metadata": {**(row.get("metadata") or {}), "cancel": response}, "updated_at": _now()})
