from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domains.products.measurements import ProductPackage
from app.domains.products.schemas import ProductCreate
from app.domains.shipping.schemas import ShippingRateRequest
from app.domains.shipping.service import ShippingService
from app.domains.shipping.states import ShipmentStatus, can_transition


def test_product_package_calculates_chargeable_weight():
    package = ProductPackage.model_validate({
        "weight": 1000,
        "weight_unit": "g",
        "dimensions": {"length": 50, "width": 40, "height": 20, "unit": "cm"},
    })
    assert package.weight_kg == Decimal("1")
    assert package.volumetric_weight_kg == Decimal("8")
    assert package.chargeable_weight_kg == Decimal("8")


def test_product_requires_positive_price_and_valid_measurements():
    with pytest.raises(ValidationError):
        ProductCreate(name="x", slug="x", price=0)


def test_shipping_request_requires_indian_pincode():
    with pytest.raises(ValidationError):
        ShippingRateRequest(cart_subtotal=100, pincode="123")


def test_shipping_transition_is_forward_only():
    assert can_transition(ShipmentStatus.IN_TRANSIT, ShipmentStatus.OUT_FOR_DELIVERY)
    assert not can_transition(ShipmentStatus.DELIVERED, ShipmentStatus.IN_TRANSIT)


def test_flat_shipping_uses_decimal_rounding():
    method = {"id": "m1", "type": "flat", "base_rate": "99.995", "is_active": True}
    result = ShippingService._compute_method_rate(method, Decimal("100"), 1, Decimal("1"))
    assert result["shipping_cost"] == Decimal("100.00")
