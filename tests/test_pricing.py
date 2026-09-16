from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.domains.pricing.service import StandardPricing, get_pricing_from_config


@pytest.fixture
def pricing() -> StandardPricing:
    return StandardPricing(
        shipping_threshold=Decimal("1499"),
        shipping_flat=Decimal("45.90"),
        currency="INR",
    )


def test_calculates_gst_and_shipping(pricing):
    result = pricing.calculate(
        [{"quantity": 2, "price_snapshot": "100", "products": {"gst_percentage": "18"}}]
    )

    assert result.subtotal == Decimal("200")
    assert result.tax == Decimal("36")
    assert result.shipping == Decimal("45.90")
    assert result.total == Decimal("281.90")


def test_free_shipping_threshold(pricing):
    result = pricing.calculate(
        [{"quantity": 1, "price_snapshot": "1499", "products": {"gst_percentage": "18"}}]
    )

    assert result.shipping == Decimal("0")


def test_rejects_missing_gst(pricing):
    with pytest.raises(Exception):
        pricing.calculate([{"quantity": 1, "price_snapshot": "100", "products": {}}])


def test_rejects_missing_pricing_configuration():
    with pytest.raises(HTTPException) as exc:
        get_pricing_from_config({"tax_enabled": True, "shipping_enabled": True})
    assert exc.value.status_code == 503


def test_zero_price_is_not_treated_as_missing(pricing):
    result = pricing.calculate(
        [{"quantity": 1, "price_snapshot": 0, "products": {"gst_percentage": 0}}]
    )
    assert result.subtotal == Decimal("0")
    assert result.tax == Decimal("0")


def test_rejects_fractional_quantity(pricing):
    with pytest.raises(HTTPException) as exc:
        pricing.calculate(
            [{"quantity": 1.5, "price_snapshot": "100", "products": {"gst_percentage": 18}}]
        )
    assert exc.value.status_code == 422


def test_rejects_non_finite_price(pricing):
    with pytest.raises(HTTPException) as exc:
        pricing.calculate(
            [{"quantity": 1, "price_snapshot": "NaN", "products": {"gst_percentage": 18}}]
        )
    assert exc.value.status_code == 500


def test_rejects_invalid_gst_rate(pricing):
    with pytest.raises(HTTPException) as exc:
        pricing.calculate(
            [{"quantity": 1, "price_snapshot": "100", "products": {"gst_percentage": 101}}]
        )
    assert exc.value.status_code == 500


def test_rejects_non_inr_checkout_configuration():
    config = {
        "tax_enabled": True,
        "shipping_enabled": True,
        "currency": "USD",
        "shipping_flat": "45.90",
        "shipping_threshold": "1499",
    }
    with pytest.raises(HTTPException) as exc:
        get_pricing_from_config(config)
    assert exc.value.status_code == 503
