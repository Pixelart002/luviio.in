from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_checkout_attempt_uses_table_fallback_when_rpc_fails(monkeypatch):
    from app.domains.payments.repository import AsyncPaymentRepository

    class _Response:
        def __init__(self, data):
            self.data = data

    rpc = MagicMock()
    rpc.return_value.execute = AsyncMock(side_effect=RuntimeError("function not found"))

    existing = MagicMock()
    existing.return_value.execute = AsyncMock(return_value=_Response(None))

    insert = MagicMock()
    insert.return_value.execute = AsyncMock(
        return_value=_Response([{"id": "attempt-fallback"}])
    )

    table = MagicMock()
    table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single = existing
    table.return_value.insert = insert

    admin = MagicMock()
    admin.rpc = rpc
    admin.table = table

    monkeypatch.setattr(
        "app.domains.payments.repository.get_async_admin_supabase",
        AsyncMock(return_value=admin),
    )

    repo = AsyncPaymentRepository()
    result = await repo.create_checkout_payment_attempt(
        "user-1",
        "11111111-1111-4111-8111-111111111111",
        15900,
        "inr",
    )

    assert result == "attempt-fallback"
    rpc.assert_called_once_with(
        "create_checkout_payment_attempt",
        {
            "p_customer_id": "user-1",
            "p_idempotency_key": "11111111-1111-4111-8111-111111111111",
            "p_provider": "stripe",
            "p_amount_paise": 15900,
            "p_currency": "inr",
        },
    )
    insert.assert_called_once_with(
        {
            "customer_id": "user-1",
            "idempotency_key": "11111111-1111-4111-8111-111111111111",
            "payment_provider": "stripe",
            "amount_paise": 15900,
            "currency": "inr",
        }
    )
