from unittest.mock import AsyncMock, Mock

import pytest


def build_service(monkeypatch):
    from app.domains.payments.service import PaymentService

    provider = Mock()
    monkeypatch.setattr(
        "app.domains.payments.service.get_payment_provider",
        lambda name="stripe": provider,
    )
    return PaymentService(), provider


@pytest.mark.asyncio
async def test_client_reported_failure_requires_order_ownership(monkeypatch):
    service, _ = build_service(monkeypatch)
    service.repo.get_order_by_payment_intent = AsyncMock(
        return_value={"id": "order-1", "customer_id": "other-user", "total_amount": 100}
    )
    service.repo.record_payment_attempt = AsyncMock()

    await service.record_client_reported_failure("user-1", "pi_other", "failed")

    service.repo.record_payment_attempt.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_refund_does_not_release_inventory_or_mark_order_refunded(monkeypatch):
    service, provider = build_service(monkeypatch)
    service.repo.record_webhook_event = AsyncMock(return_value=True)
    service.repo.mark_webhook_event_processed = AsyncMock()
    service.repo.get_order_by_payment_intent = AsyncMock(
        return_value={
            "id": "order-1",
            "customer_id": "user-1",
            "status": "paid",
            "shipping_email": "user@example.com",
        }
    )
    service.repo.record_provider_refund_event = AsyncMock(
        return_value={
            "status": "succeeded",
            "amount": 10,
            "total_refunded": 10,
            "fully_refunded": False,
        }
    )
    service.inventory.commit_reservation = AsyncMock()
    service.inventory.release_reservation = AsyncMock()
    provider.verify_webhook.return_value = {
        "id": "evt_partial_refund",
        "type": "charge.refunded",
        "data": {
            "object": {
                "object": "charge",
                "id": "ch_1",
                "payment_intent": "pi_1",
                "currency": "inr",
                "refunds": {
                    "data": [{
                        "id": "re_1",
                        "amount": 1000,
                        "created": 100,
                        "status": "succeeded",
                        "currency": "inr",
                    }]
                },
            }
        },
    }

    await service.handle_webhook(b"payload", "signature")

    service.inventory.release_reservation.assert_not_awaited()
    service.repo.update_order_status_via_rpc = AsyncMock()
    service.repo.update_order_status_via_rpc.assert_not_awaited()
    service.repo.mark_webhook_event_processed.assert_awaited_once_with("evt_partial_refund")


@pytest.mark.asyncio
async def test_replacement_retry_reserves_slot_before_provider_creation(monkeypatch):
    service, provider = build_service(monkeypatch)

    class RPCResult:
        data = {"reservation_id": "res-1", "attempt_number": 2}

    class BoundResult:
        data = True

    class Admin:
        def __init__(self):
            self.calls = []

        def rpc(self, name, args):
            self.calls.append((name, args))
            result = RPCResult() if name == "reserve_payment_retry_replacement" else BoundResult()

            class Query:
                async def execute(self):
                    return result

            return Query()

    admin = Admin()
    monkeypatch.setattr(
        "app.domains.payments.service.get_async_admin_supabase",
        AsyncMock(return_value=admin),
    )
    service.repo.update_order_payment_intent = AsyncMock(return_value=True)
    service.repo.record_payment_attempt = AsyncMock()
    provider.create_payment_intent.return_value = {
        "id": "pi_new",
        "client_secret": "secret",
        "status": "requires_payment_method",
    }
    provider.update_intent_metadata.return_value = {"id": "pi_new"}

    result = await service._create_and_link_replacement_intent("user-1", "order-1", 10000)

    assert result["payment_intent_id"] == "pi_new"
    assert admin.calls[0][0] == "reserve_payment_retry_replacement"
    assert admin.calls[1][0] == "bind_payment_retry_reservation"
    assert admin.calls[0][0] in admin.calls[0][0]
    provider.create_payment_intent.assert_called_once()
    assert provider.create_payment_intent.call_args.args[-1] == "retry_slot_res-1"
