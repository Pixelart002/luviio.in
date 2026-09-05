import pytest
from fastapi import HTTPException

from app.permissions.policies.payment_policies import PaymentPolicy


VALID_PRODUCT = {
    "name": "Test Product",
    "is_active": True,
    "stock": 10,
    "price": "100.00",
    "hsn_code": "7318",
    "gst_percentage": 18,
}


def assert_http_503(mutated_product):
    with pytest.raises(HTTPException) as exc:
        PaymentPolicy.assert_stock_availability(1, mutated_product)
    assert exc.value.status_code == 503


def test_checkout_accepts_complete_financial_product():
    PaymentPolicy.assert_stock_availability(1, VALID_PRODUCT)


@pytest.mark.parametrize("field", ["price", "hsn_code", "gst_percentage"])
def test_checkout_fails_closed_when_financial_field_is_missing(field):
    product = dict(VALID_PRODUCT)
    product[field] = None
    assert_http_503(product)


def test_checkout_rejects_invalid_quantity():
    with pytest.raises(HTTPException) as exc:
        PaymentPolicy.assert_stock_availability(0, VALID_PRODUCT)
    assert exc.value.status_code == 422


def test_checkout_rejects_inactive_product():
    product = dict(VALID_PRODUCT)
    product["is_active"] = False
    with pytest.raises(HTTPException) as exc:
        PaymentPolicy.assert_stock_availability(1, product)
    assert exc.value.status_code == 409
