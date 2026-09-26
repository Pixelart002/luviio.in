"""Shipping domain routes: checkout rates plus complete fulfillment lifecycle."""
from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.constants.shipping_messages import ShippingMessages
from app.core.dependencies import get_user_id_strict, require_permission
from app.domains.shipping.provider_repository import ShippingProviderRepository
from app.domains.shipping.provider_service import ShippingProviderService
from app.domains.shipping.schemas import (
    ShippingMethodCreate,
    ShippingMethodUpdate,
    ShippingRateRequest,
)
from app.domains.shipping.service import ShippingService
from app.permissions.shipping import ShippingPermissions
from app.utils.response import success_response

router = APIRouter(prefix="/shipping", tags=["Shipping"])
_service = ShippingService()
_provider_service = ShippingProviderService()
_provider_repo = ShippingProviderRepository()

@router.get("/methods", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.READ))])
async def list_methods(active_only: bool = True):
    data = await _service.list_methods(active_only)
    return success_response(data={"items": data}, message=ShippingMessages.METHODS_FETCHED)

@router.post("/rate", status_code=200)
async def compute_rate(payload: ShippingRateRequest):
    # Legacy flat-rate calculation is no longer a checkout source of truth.
    # Keep this endpoint compatible for existing callers, but route it to the
    # same live Shiprocket quote used by payment/COD checkout.
    if not payload.pincode:
        raise HTTPException(status_code=422, detail="Delivery PIN code is required for live shipping.")
    data = await _provider_service.quote_for_checkout(
        delivery_postcode=str(payload.pincode),
        weight_kg=float(payload.total_weight_kg or 0.5),
        cod=False,
        declared_value=float(payload.cart_subtotal or 0),
    )
    selected = data["selected"]
    return success_response(
        data={
            "shipping_cost": selected["shipping_cost"],
            "method": selected,
            "method_id": selected.get("courier_id"),
            "applied_type": "shiprocket_live",
            "provider": "shiprocket",
            "quotes": data.get("quotes", []),
        },
        message="Live Shiprocket shipping rate fetched.",
    )

@router.post("/manage", status_code=201, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def create_method(payload: ShippingMethodCreate):
    return success_response(data=await _service.create(payload.model_dump()), message=ShippingMessages.METHOD_CREATED)

@router.patch("/manage/{method_id}", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def update_method(method_id: str, payload: ShippingMethodUpdate):
    return success_response(data=await _service.update(method_id, payload.model_dump(exclude_unset=True)), message=ShippingMessages.METHOD_UPDATED)

@router.post("/manage/{method_id}/activate", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def activate_method(method_id: str):
    return success_response(data=await _service.activate(method_id), message="Shipping method activated successfully.")

@router.get("/provider/serviceability", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.READ))])
async def provider_serviceability(pickup_postcode: str, delivery_postcode: str, weight_kg: float = 0.5, cod: bool = False, declared_value: float | None = None, provider: str = "shiprocket"):
    data = await _provider_service.serviceability(provider, pickup_postcode, delivery_postcode, weight_kg, cod, declared_value)
    return success_response(data=data, message="Shipping provider serviceability fetched.")

@router.get("/provider/rate", status_code=200)
async def provider_rate(delivery_postcode: str, weight_kg: float = 0.5, cod: bool = False, declared_value: float | None = None, user_id: str = Depends(get_user_id_strict)):
    # Customer checkout endpoint: authentication only. Do not require the
    # privileged shipping.read/MFA permission used by admin fulfillment APIs.
    data = await _provider_service.quote_for_checkout(
        delivery_postcode=delivery_postcode,
        weight_kg=weight_kg,
        cod=cod,
        declared_value=declared_value,
    )
    return success_response(data=data, message="Live Shiprocket shipping rates fetched.")

@router.get("/provider/shipments", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.READ))])
async def list_provider_shipments(status_filter: str | None = None, limit: int = 100):
    return success_response(data={"items": await _provider_repo.list_recent(status_filter, limit)}, message="Fulfillment shipments fetched.")

@router.post("/provider/orders/{order_id}", status_code=201, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def create_provider_shipment(
    order_id: str,
    pickup_location: str | None = None,
    weight_kg: float | None = None,
    length_cm: float | None = None,
    breadth_cm: float | None = None,
    height_cm: float | None = None,
    provider: str = "shiprocket",
):
    # All values are optional because the backend now derives shipment data
    # from the saved order/product records and Shiprocket defaults/config.
    data = await _provider_service.create_for_order(
        order_id, provider, pickup_location, weight_kg, length_cm, breadth_cm, height_cm
    )
    return success_response(data=data, message="Shipment created with provider.")

@router.post("/provider/shipments/{shipment_id}/awb", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def assign_awb(shipment_id: str, courier_id: int | None = None):
    return success_response(data=await _provider_service.assign_awb(shipment_id, courier_id), message="Courier/AWB assigned.")

@router.post("/provider/shipments/{shipment_id}/process", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def process_provider_shipment(shipment_id: str):
    return success_response(
        data=await _provider_service.process_shipment(shipment_id),
        message="Shipment fulfillment workflow completed/resumed.",
    )

@router.post("/provider/shipments/{shipment_id}/pickup", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def schedule_pickup(shipment_id: str):
    return success_response(data=await _provider_service.schedule_pickup(shipment_id), message="Pickup scheduled.")

@router.post("/provider/shipments/{shipment_id}/label", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def generate_label(shipment_id: str):
    return success_response(data=await _provider_service.generate_label(shipment_id), message="Shipping label generated.")

@router.post("/provider/shipments/{shipment_id}/manifest", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def generate_manifest(shipment_id: str):
    return success_response(data=await _provider_service.generate_manifest(shipment_id), message="Manifest generated.")

@router.post("/provider/shipments/{shipment_id}/invoice", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def generate_provider_invoice(shipment_id: str):
    return success_response(data=await _provider_service.print_invoice(shipment_id), message="Courier invoice generated.")

@router.post("/provider/shipments/{shipment_id}/sync", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def sync_tracking(shipment_id: str):
    return success_response(data=await _provider_service.sync_tracking(shipment_id), message="Shipment tracking synchronized.")

@router.post("/provider/shipments/{shipment_id}/cancel", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))])
async def cancel_provider_shipment(shipment_id: str):
    return success_response(data=await _provider_service.cancel(shipment_id), message="Provider shipment cancelled.")

@router.get("/provider/track/{tracking_number}", status_code=200, dependencies=[Depends(require_permission(ShippingPermissions.READ))])
async def provider_tracking(tracking_number: str, provider: str = "shiprocket"):
    return success_response(data=await _provider_service.track(provider, tracking_number), message="Shipping provider tracking fetched.")

async def _validate_shipping_webhook_secret(x_api_key: str | None, x_luviio_shipping_secret: str | None) -> None:
    expected = os.getenv("LUVIIO_SHIPPING_WEBHOOK_SECRET")
    supplied = x_api_key or x_luviio_shipping_secret
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid shipping webhook signature.")


@router.post("/provider/webhook", status_code=200)
async def shiprocket_webhook(
    payload: dict[str, Any],
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    x_luviio_shipping_secret: str | None = Header(default=None),
):
    # Shiprocket requires the webhook URL to avoid provider-name keywords and
    # sends its configured security token in x-api-key. Keep the public URL
    # provider-neutral while retaining the legacy header for migration.
    await _validate_shipping_webhook_secret(x_api_key, x_luviio_shipping_secret)
    data = await _provider_service.handle_webhook("shiprocket", payload)
    return success_response(data=data, message="Shipping webhook processed.")


@router.post("/provider/webhook/{provider}", status_code=200)
async def provider_webhook(
    provider: str,
    payload: dict[str, Any],
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    x_luviio_shipping_secret: str | None = Header(default=None),
):
    await _validate_shipping_webhook_secret(x_api_key, x_luviio_shipping_secret)
    data = await _provider_service.handle_webhook(provider, payload)
    return success_response(data=data, message="Shipping webhook processed.")

@router.get("/my/{order_number}", status_code=200)
async def my_shipment(order_number: str, user_id: str = Depends(get_user_id_strict)):
    from app.core.supabase import get_async_admin_supabase

    sb = await get_async_admin_supabase()
    order_res = await sb.table("orders").select("id,order_number,customer_id").eq("order_number", order_number.strip()).eq("customer_id", user_id).maybe_single().execute()
    order = order_res.data if order_res else None
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    row = await _provider_repo.get_by_order(str(order["id"]), "shiprocket")
    return success_response(data=row or {"status": "not_booked"}, message="Shipment status fetched.")
