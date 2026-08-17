import importlib
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.fixture
def service():
    with patch("app.services.payments.service.get_payment_provider") as get_provider:
        provider = Mock()
        get_provider.return_value = provider
        mod = importlib.import_module("app.services.payments.service")
        svc = mod.PaymentService()
        svc.provider = provider
        yield svc, provider


def test_paise_round_half_up(service):
    svc, _ = service
    assert svc._paise("10.005") == 1001
    assert svc._paise("10") == 1000


def test_clean_order_number(service):
    svc, _ = service
    number = svc._generate_clean_order_number()
    assert number.startswith("ORD-")
    assert len(number) == 12


@pytest.mark.asyncio
async def test_confirm_payment_rejects_invalid_payment_intent(service):
    svc, _ = service
    with pytest.raises(Exception) as exc:
        await svc.confirm_payment("user-1", "127.0.0.1", "", "test@example.com")
    assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_create_intent_rejects_invalid_idempotency_key(service):
    svc, _ = service
    with pytest.raises(Exception) as exc:
        await svc.create_intent(
            user_id="user-1",
            client_ip="127.0.0.1",
            idempotency_key="not-a-uuid",
            address_id="addr-1",
        )
    assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_confirm_payment_rejects_non_succeeded_intent(service):
    svc, provider = service
    provider.retrieve_intent.return_value = {
        "id": "pi_test",
        "status": "requires_payment_method",
    }
    with pytest.raises(Exception) as exc:
        await svc.confirm_payment("user-1", "127.0.0.1", "pi_test", "test@example.com")
    assert getattr(exc.value, "status_code", None) == 402
