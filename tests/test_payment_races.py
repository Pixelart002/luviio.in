from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


def build_service(monkeypatch):
    from app.domains.payments.service import PaymentService

    provider = __import__("unittest.mock", fromlist=["Mock"]).Mock()
    monkeypatch.setattr(
        "app.domains.payments.service.get_payment_provider",
        lambda name="stripe": provider,
    )
    return PaymentService(), provider


@pytest.mark.asyncio
async def test_success_after_cancel_is_refunded(monkeypatch):
    service, provider = build_service(monkeypatch)
    service.repo.get_order_by_id = AsyncMock(
        return_value={"id": "order-1", "customer_id": "user-1", "status": "pending"}
    )
    service.repo.settle_order_transaction = AsyncMock(return_value="ORDER_ALREADY_CANCELLED")
    provider.retrieve_intent.return_value = {
        "id": "pi_race",
        "status": "succeeded",
        "amount": 1000,
        "payment_method_types": ["card"],
        "metadata": {"order_id": "order-1"},
    }

    with pytest.raises(HTTPException) as error:
        await service.confirm_payment("user-1", "127.0.0.1", "pi_race", "user@example.com")

    assert error.value.status_code == 409
    provider.process_refund.assert_called_once_with("pi_race")
    service.repo.settle_order_transaction.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_success_after_settlement_is_idempotent(monkeypatch):
    service, provider = build_service(monkeypatch)
    service.repo.get_order_by_id = AsyncMock(
        return_value={"id": "order-1", "customer_id": "user-1", "status": "pending"}
    )
    service.repo.settle_order_transaction = AsyncMock(return_value="ALREADY_PAID")
    provider.retrieve_intent.return_value = {
        "id": "pi_same",
        "status": "succeeded",
        "amount": 1000,
        "payment_method_types": ["card"],
        "metadata": {"order_id": "order-1"},
    }

    first = await service.confirm_payment("user-1", "127.0.0.1", "pi_same", "user@example.com")
    second = await service.confirm_payment("user-1", "127.0.0.1", "pi_same", "user@example.com")

    assert first["status"] == "paid"
    assert second["status"] == "paid"
    assert service.repo.settle_order_transaction.await_count == 2
    provider.process_refund.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_webhook_delivery_does_not_settle_twice(monkeypatch):
    service, provider = build_service(monkeypatch)
    service.repo.record_webhook_event = AsyncMock(return_value=False)
    service.repo.get_order_by_payment_intent = AsyncMock()
    service.repo.settle_order_transaction = AsyncMock()
    provider.verify_webhook.return_value = {
        "id": "evt_duplicate",
        "type": "payment_intent.succeeded",
        "data": {"object": {"object": "payment_intent", "id": "pi_duplicate"}},
    }

    await service.handle_webhook(b"payload", "signature")

    service.repo.record_webhook_event.assert_awaited_once_with(
        "evt_duplicate", "payment_intent.succeeded", "pi_duplicate"
    )
    service.repo.get_order_by_payment_intent.assert_not_awaited()
    service.repo.settle_order_transaction.assert_not_awaited()
