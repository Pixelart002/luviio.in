from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.domains.shipping.calculator import calculate_settings_shipping


@pytest.mark.parametrize(
    "subtotal,enabled,threshold,flat_rate,expected",
    [
        (Decimal("1498.99"), True, "1499", "45.90", Decimal("45.90")),
        (Decimal("1499.00"), True, "1499", "45.90", Decimal("0.00")),
        (Decimal("1800.00"), True, "1499", "45.90", Decimal("0.00")),
        (Decimal("1000.00"), False, "1499", "45.90", Decimal("0.00")),
        (Decimal("1000.00"), "true", "1499", "45.90", Decimal("45.90")),
    ],
)
def test_settings_shipping_boundaries(subtotal, enabled, threshold, flat_rate, expected):
    assert calculate_settings_shipping(
        subtotal=subtotal,
        shipping_enabled=enabled,
        threshold=threshold,
        flat_rate=flat_rate,
    ) == expected


def test_settings_shipping_rejects_invalid_enabled_value():
    with pytest.raises(HTTPException) as exc:
        calculate_settings_shipping(
            subtotal=Decimal("1000"),
            shipping_enabled="maybe",
            threshold="1499",
            flat_rate="45.90",
        )
    assert exc.value.status_code == 503
