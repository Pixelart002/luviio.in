import pytest
from unittest.mock import AsyncMock

from app.domains.orders import customer_cancellation


class FakeOrderRepo:
    async def get_order_by_id(self, _order_identifier):
        return {
            "id": "order-1",
            "customer_id": "user-1",
            "order_number": "ORD-COD-0001",
            "status": "paid",
            "payment_method": "cod",
            "payment_provider": "cod",
            "provider_payment_id": "cod:test-reference",
            "stripe_payment_intent": None,
        }


class FakeOrderService:
    def __init__(self):
        self.repo = FakeOrderRepo()


class FakeEventBus:
    def __init__(self):
        self.publish_durable = AsyncMock()


class FakePaymentPort:
    def __init__(self):
        self.refund_payment_intent = AsyncMock(return_value=True)


class FakePaymentRepo:
    def __init__(self):
        self.record_refund_accounting = AsyncMock(return_value="REFUNDED_ACCOUNTED")


@pytest.mark.asyncio
async def test_paid_cod_order_cancels_without_stripe_payment_reference(monkeypatch):
    payment_port = FakePaymentPort()
    payment_repo = FakePaymentRepo()
    event_bus = FakeEventBus()
    monkeypatch.setattr(customer_cancellation, "AsyncPaymentRepository", lambda: payment_repo)
    monkeypatch.setattr(customer_cancellation, "OrderService", FakeOrderService)
    monkeypatch.setattr(
        customer_cancellation.OrderPolicy,
        "assert_can_view",
        lambda order, user_id: order,
    )
    monkeypatch.setattr(
        customer_cancellation,
        "release_stock_for_customer_cancellation",
        AsyncMock(return_value={"id": "order-1", "status": "cancelled"}),
    )
    monkeypatch.setattr(customer_cancellation, "get_event_bus", lambda: event_bus)

    result = await customer_cancellation.cancel_customer_order(
        "ORD-COD-0001",
        "user-1",
        payment_port,
    )

    assert result["status"] == "cancelled"
    assert result["order_number"] == "ORD-COD-0001"
    payment_port.refund_payment_intent.assert_not_awaited()
    event_bus.publish_durable.assert_awaited_once()


@pytest.mark.asyncio
async def test_paid_stripe_order_still_requires_and_refunds_payment_intent(monkeypatch):
    payment_port = FakePaymentPort()
    payment_repo = FakePaymentRepo()
    event_bus = FakeEventBus()
    monkeypatch.setattr(customer_cancellation, "AsyncPaymentRepository", lambda: payment_repo)

    class StripeOrderRepo:
        async def get_order_by_id(self, _order_identifier):
            return {
                "id": "order-2",
                "customer_id": "user-1",
                "order_number": "ORD-CARD-0001",
                "status": "paid",
                "payment_method": "card",
                "payment_provider": "stripe",
                "stripe_payment_intent": "pi_test_123",
            }

    class StripeOrderService:
        def __init__(self):
            self.repo = StripeOrderRepo()

    monkeypatch.setattr(customer_cancellation, "OrderService", StripeOrderService)
    monkeypatch.setattr(
        customer_cancellation.OrderPolicy,
        "assert_can_view",
        lambda order, user_id: order,
    )
    monkeypatch.setattr(
        customer_cancellation,
        "release_stock_for_customer_cancellation",
        AsyncMock(return_value={"id": "order-2", "status": "refunded"}),
    )
    monkeypatch.setattr(customer_cancellation, "get_event_bus", lambda: event_bus)

    result = await customer_cancellation.cancel_customer_order(
        "ORD-CARD-0001",
        "user-1",
        payment_port,
    )

    assert result["status"] == "refunded"
    payment_port.refund_payment_intent.assert_awaited_once_with("pi_test_123")
    payment_repo.record_refund_accounting.assert_awaited_once()
