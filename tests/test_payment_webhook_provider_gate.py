"""Webhook delivery must not depend on whether new checkouts are enabled."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.payments import router as payment_router


class FakeRequest:
    def __init__(self, headers=None, payload=b'{"id":"evt_test"}'):
        self.headers = headers or {}
        self._payload = payload

    async def body(self):
        return self._payload


@pytest.mark.asyncio
async def test_signed_stripe_webhook_is_processed_when_provider_is_disabled(monkeypatch):
    handle_webhook = AsyncMock()

    class FakePaymentService:
        def __init__(self):
            pass

        async def handle_webhook(self, payload, signature):
            await handle_webhook(payload, signature)

    async def fail_if_checkout_gate_is_called(*args, **kwargs):
        raise AssertionError("Webhook must not be gated by checkout provider enablement")

    monkeypatch.setattr(payment_router, "PaymentService", FakePaymentService)
    monkeypatch.setattr(payment_router, "_require_provider_enabled", fail_if_checkout_gate_is_called)

    response = await payment_router.payment_webhook(
        FakeRequest(headers={"stripe-signature": "valid-test-signature"}),
        "stripe",
    )

    assert response.status_code == 200
    handle_webhook.assert_awaited_once_with(b'{"id":"evt_test"}', "valid-test-signature")


@pytest.mark.asyncio
async def test_webhook_rejects_unregistered_provider_without_checkout_gate(monkeypatch):
    async def fail_if_checkout_gate_is_called(*args, **kwargs):
        raise AssertionError("Unknown provider should be rejected before provider activation lookup")

    monkeypatch.setattr(payment_router, "_require_provider_enabled", fail_if_checkout_gate_is_called)

    response = await payment_router.payment_webhook(
        FakeRequest(headers={"x-payment-signature": "signature"}),
        "provider-not-installed",
    )

    assert response.status_code == 404
    assert response.body == b"Unknown payment provider"


@pytest.mark.asyncio
async def test_webhook_still_requires_provider_signature(monkeypatch):
    handle_webhook = AsyncMock()

    class FakePaymentService:
        def __init__(self):
            pass

        async def handle_webhook(self, payload, signature):
            await handle_webhook(payload, signature)

    monkeypatch.setattr(payment_router, "PaymentService", FakePaymentService)

    response = await payment_router.payment_webhook(FakeRequest(), "stripe")

    assert response.status_code == 400
    handle_webhook.assert_not_awaited()
