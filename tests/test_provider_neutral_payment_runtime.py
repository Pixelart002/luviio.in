from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_repository_settlement_uses_provider_neutral_rpc(monkeypatch):
    from app.domains.payments.repository import AsyncPaymentRepository

    class _Response:
        data = "SETTLED"

    execute = AsyncMock(return_value=_Response())
    rpc = MagicMock()
    rpc.return_value.execute = execute

    admin = MagicMock()
    admin.rpc = rpc
    monkeypatch.setattr(
        "app.domains.payments.repository.get_async_admin_supabase",
        AsyncMock(return_value=admin),
    )

    from app.integrations.payments.context import payment_provider_context

    repo = AsyncPaymentRepository()
    with payment_provider_context("razorpay"):
        result = await repo.settle_order_transaction(
            order_id="order-1",
            pi_id="pay_test_123",
            amount=100.0,
            user_id="user-1",
            payment_method="upi",
            stripe_currency="INR",
        )

    assert result == "SETTLED"
    rpc.assert_called_once_with(
        "settle_payment_transaction",
        {
            "p_order_id": "order-1",
            "p_provider": "razorpay",
            "p_provider_payment_id": "pay_test_123",
            "p_amount": 100.0,
            "p_user_id": "user-1",
            "p_payment_method": "upi",
            "p_currency": "INR",
        },
    )


@pytest.mark.asyncio
async def test_repository_records_provider_neutral_attempt(monkeypatch):
    from app.domains.payments.repository import AsyncPaymentRepository
    from app.integrations.payments.context import payment_provider_context

    class _Response:
        data = None

    execute = AsyncMock(return_value=_Response())
    rpc = MagicMock()
    rpc.return_value.execute = execute

    admin = MagicMock()
    admin.rpc = rpc
    monkeypatch.setattr(
        "app.domains.payments.repository.get_async_admin_supabase",
        AsyncMock(return_value=admin),
    )

    repo = AsyncPaymentRepository()
    with payment_provider_context("cashfree"):
        await repo.record_payment_attempt(
            order_id="order-1",
            user_id="user-1",
            pi_id="cf_test_123",
            amount=250.0,
            status="requires_payment_method",
            payment_method="upi",
        )

    rpc.assert_called_once_with(
        "record_payment_attempt_provider",
        {
            "p_order_id": "order-1",
            "p_user_id": "user-1",
            "p_provider": "cashfree",
            "p_provider_payment_id": "cf_test_123",
            "p_amount": 250.0,
            "p_status": "requires_payment_method",
            "p_payment_method": "upi",
            "p_error_code": None,
            "p_error_message": None,
            "p_ip_address": None,
            "p_user_agent": None,
        },
    )
