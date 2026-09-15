import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.constants.payment_messages import PaymentSecurityMessages


def build_service(monkeypatch):
    from app.domains.payments.service import PaymentService

    provider = Mock()
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


@pytest.mark.asyncio
async def test_confirm_cancelled_order_refund_failure_is_pending(monkeypatch):
    service, provider = build_service(monkeypatch)
    service.repo.get_order_by_id = AsyncMock(
        return_value={"id": "order-1", "customer_id": "user-1", "status": "pending"}
    )
    service.repo.settle_order_transaction = AsyncMock(return_value="ORDER_ALREADY_CANCELLED")
    provider.retrieve_intent.return_value = {
        "id": "pi_fail",
        "status": "succeeded",
        "amount": 1000,
        "payment_method_types": ["card"],
        "metadata": {"order_id": "order-1"},
    }
    provider.process_refund.side_effect = RuntimeError("refund unavailable")

    with pytest.raises(HTTPException) as error:
        await service.confirm_payment("user-1", "127.0.0.1", "pi_fail", "user@example.com")

    assert error.value.status_code == 503
    assert error.value.detail == PaymentSecurityMessages.ORDER_CANCELLED_REFUND_PENDING
    provider.process_refund.assert_called_once_with("pi_fail")


@pytest.mark.asyncio
async def test_retry_cancelled_order_refund_failure_is_pending(monkeypatch):
    service, provider = build_service(monkeypatch)
    service.repo.get_order_by_id = AsyncMock(
        return_value={"id": "order-1", "customer_id": "user-1", "status": "pending", "total_amount": 10}
    )
    service.repo.settle_order_transaction = AsyncMock(return_value="ORDER_ALREADY_CANCELLED")
    provider.retrieve_intent.return_value = {
        "id": "pi_fail",
        "status": "succeeded",
        "amount": 1000,
        "payment_method_types": ["card"],
    }
    provider.process_refund.side_effect = RuntimeError("refund unavailable")

    with pytest.raises(HTTPException) as error:
        await service.retry_payment("user-1", "order-1")

    assert error.value.status_code == 503
    assert error.value.detail == PaymentSecurityMessages.ORDER_CANCELLED_REFUND_PENDING
    provider.process_refund.assert_called_once_with("pi_fail")


@pytest.mark.asyncio
async def test_webhook_refund_failure_is_left_unprocessed(monkeypatch):
    service, provider = build_service(monkeypatch)
    service.repo.record_webhook_event = AsyncMock(return_value=True)
    service.repo.get_order_by_payment_intent = AsyncMock(
        return_value={
            "id": "order-1",
            "customer_id": "user-1",
            "status": "pending",
            "shipping_email": "user@example.com",
        }
    )
    service.repo.settle_order_transaction = AsyncMock(return_value="ORDER_ALREADY_CANCELLED")
    service.repo.mark_webhook_event_processed = AsyncMock()
    provider.verify_webhook.return_value = {
        "id": "evt_refund_fail",
        "type": "payment_intent.succeeded",
        "data": {"object": {"object": "payment_intent", "id": "pi_fail"}},
    }
    provider.process_refund.side_effect = RuntimeError("refund unavailable")

    with pytest.raises(RuntimeError, match="webhook must remain retryable"):
        await service.handle_webhook(b"payload", "signature")

    service.repo.mark_webhook_event_processed.assert_not_awaited()
    provider.process_refund.assert_called_once_with("pi_fail")


@pytest.mark.asyncio
async def test_concurrent_confirmations_only_one_settles(monkeypatch):
    service, provider = build_service(monkeypatch)
    service.repo.get_order_by_id = AsyncMock(
        return_value={"id": "order-1", "customer_id": "user-1", "status": "pending"}
    )
    service.repo.settle_order_transaction = AsyncMock(side_effect=["SETTLED", "ALREADY_PAID"])
    provider.retrieve_intent.return_value = {
        "id": "pi_concurrent",
        "status": "succeeded",
        "amount": 1000,
        "payment_method_types": ["card"],
        "metadata": {"order_id": "order-1"},
    }

    results = await asyncio.gather(
        service.confirm_payment("user-1", "127.0.0.1", "pi_concurrent", "user@example.com"),
        service.confirm_payment("user-1", "127.0.0.1", "pi_concurrent", "user@example.com"),
    )

    assert [result["status"] for result in results] == ["paid", "paid"]
    assert service.repo.settle_order_transaction.await_count == 2
    provider.process_refund.assert_not_called()


@pytest.mark.asyncio
async def test_retry_and_webhook_same_payment_intent_converge(monkeypatch):
    service, provider = build_service(monkeypatch)
    order = {
        "id": "order-1",
        "customer_id": "user-1",
        "status": "pending",
        "total_amount": 10,
        "stripe_payment_intent": "pi_shared",
        "shipping_email": "user@example.com",
    }
    service.repo.get_order_by_id = AsyncMock(return_value=order.copy())
    service.repo.get_order_by_payment_intent = AsyncMock(return_value=order.copy())
    service.repo.settle_order_transaction = AsyncMock(side_effect=["SETTLED", "ALREADY_PAID"])
    service.repo.mark_webhook_event_processed = AsyncMock()
    service.repo.record_webhook_event = AsyncMock(return_value=True)
    provider.retrieve_intent.return_value = {
        "id": "pi_shared",
        "status": "succeeded",
        "amount": 1000,
        "payment_method_types": ["card"],
    }
    provider.verify_webhook.return_value = {
        "id": "evt_shared",
        "type": "payment_intent.succeeded",
        "data": {"object": {"object": "payment_intent", "id": "pi_shared"}},
    }

    retry_result, _ = await asyncio.gather(
        service.retry_payment("user-1", "order-1"),
        service.handle_webhook(b"payload", "signature"),
    )

    assert retry_result["status"] == "paid"
    assert service.repo.settle_order_transaction.await_count == 2
    service.repo.mark_webhook_event_processed.assert_awaited_once_with("evt_shared")
    provider.process_refund.assert_not_called()
