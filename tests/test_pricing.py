from decimal import Decimal

import pytest

from app.domains.pricing.service import StandardPricing


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
