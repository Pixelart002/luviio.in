"""Shipping Domain — Router."""

from fastapi import APIRouter, Depends, status

from app.constants.shipping_messages import ShippingMessages
from app.core.dependencies import require_permission
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


@router.get(
    "/methods",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(ShippingPermissions.READ))],
)
async def list_methods(active_only: bool = True):
    data = await _service.list_methods(active_only)
    return success_response(data={"items": data}, message=ShippingMessages.METHODS_FETCHED)


@router.post(
    "/rate",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(ShippingPermissions.READ))],
)
async def compute_rate(payload: ShippingRateRequest):
    data = await _service.compute_rate(
        subtotal=payload.cart_subtotal,
        item_count=payload.item_count,
        weight_kg=payload.total_weight_kg,
        method_id=payload.method_id,
        pincode=payload.pincode,
    )
    return success_response(data=data, message=ShippingMessages.RATE_COMPUTED)


@router.post(
    "/manage",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))],
)
async def create_method(payload: ShippingMethodCreate):
    data = await _service.create(payload.model_dump())
    return success_response(data=data, message=ShippingMessages.METHOD_CREATED)


@router.patch(
    "/manage/{method_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))],
)
async def update_method(method_id: str, payload: ShippingMethodUpdate):
    data = await _service.update(method_id, payload.model_dump(exclude_unset=True))
    return success_response(data=data, message=ShippingMessages.METHOD_UPDATED)


@router.post(
    "/manage/{method_id}/activate",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))],
)
async def activate_method(method_id: str):
    data = await _service.activate(method_id)
    return success_response(data=data, message="Shipping method activated successfully.")


@router.get(
    "/provider/serviceability",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(ShippingPermissions.READ))],
)
async def provider_serviceability(
    pickup_postcode: str,
    delivery_postcode: str,
    weight_kg: float = 0.5,
    cod: bool = False,
    provider: str = "shiprocket",
):
    data = await _provider_service.serviceability(
        provider_key=provider,
        pickup_postcode=pickup_postcode,
        delivery_postcode=delivery_postcode,
        weight_kg=weight_kg,
        cod=cod,
    )
    return success_response(data=data, message="Shipping provider serviceability fetched.")


@router.post(
    "/provider/orders/{order_id}",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(ShippingPermissions.UPDATE))],
)
async def create_provider_shipment(
    order_id: str,
    pickup_location: str,
    weight_kg: float,
    length_cm: float,
    breadth_cm: float,
    height_cm: float,
    provider: str = "shiprocket",
):
    data = await _provider_service.create_for_order(
        order_id=order_id,
        provider_key=provider,
        pickup_location=pickup_location,
        weight_kg=weight_kg,
        length_cm=length_cm,
        breadth_cm=breadth_cm,
        height_cm=height_cm,
    )
    return success_response(data=data, message="Shipment created with provider.")


@router.get(
    "/provider/track/{tracking_number}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(ShippingPermissions.READ))],
)
async def provider_tracking(
    tracking_number: str,
    provider: str = "shiprocket",
):
    data = await _provider_service.track(provider, tracking_number)
    return success_response(data=data, message="Shipment tracking fetched.")
