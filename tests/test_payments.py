from unittest.mock import Mock

import pytest


def build_service(monkeypatch):
    from app.services.payments.service import PaymentService

    provider = Mock()
    monkeypatch.setattr(
        "app.services.payments.service.get_payment_provider",
        lambda name="stripe": provider,
    )
    return PaymentService(), provider


def test_registry_is_case_insensitive():
    from app.integrations.payments.registry import get_payment_provider
    from app.integrations.payments.stripe_impl import StripeProvider

    assert isinstance(get_payment_provider("stripe"), StripeProvider)
    assert isinstance(get_payment_provider("STRIPE"), StripeProvider)


def test_money_and_order_helpers(monkeypatch):
    service, _ = build_service(monkeypatch)

    assert service._paise("10.005") == 1001
    assert service._paise("10") == 1000
    assert service._generate_clean_order_number().startswith("ORD-")


@pytest.mark.asyncio
async def test_checkout_rejects_invalid_idempotency_key(monkeypatch):
    service, _ = build_service(monkeypatch)

    with pytest.raises(Exception) as error:
        await service.create_intent(
            user_id="user-1",
            client_ip="127.0.0.1",
            idempotency_key="invalid",
            address_id="address-1",
        )

    assert getattr(error.value, "status_code", None) == 400
