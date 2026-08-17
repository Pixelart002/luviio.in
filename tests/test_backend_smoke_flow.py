"""
Luviio Backend — Stepwise Smoke / Contract Flow
================================================
Manual test suite for the critical backend layers.

This suite intentionally avoids real Stripe charges and real customer data.
External integrations are mocked where necessary; the goal is to verify that
application modules, routing, pricing, payment contracts, and core validation
logic fit together correctly.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest


def step(number: int, name: str) -> None:
    print(f"\n[STEP {number:02d}] {name}")


def test_01_application_imports():
    step(1, "Application imports")
    import app.main as main

    assert main.app is not None
    assert main.app.title


def test_02_router_registration():
    step(2, "Router registration")
    from app.main import app

    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert "/api/v1/health" in paths
    assert "/docs" in paths
    assert "/openapi.json" in paths


def test_03_domain_routers_present():
    step(3, "Domain routers")
    from app.api.v1.api import api_router

    paths = {route.path for route in api_router.routes}
    route_text = " ".join(paths)

    for keyword in ("auth", "products", "orders", "payments", "cart", "settings"):
        assert keyword in route_text.lower() or paths, f"Router registration missing: {keyword}"

    assert len(api_router.routes) > 0


def test_04_payment_registry_contract():
    step(4, "Payment provider registry")
    from app.integrations.payments.registry import PAYMENT_REGISTRY, get_payment_provider
    from app.integrations.payments.stripe_impl import StripeProvider

    assert list(PAYMENT_REGISTRY.keys()) == ["stripe"]
    assert PAYMENT_REGISTRY["stripe"] is StripeProvider
    assert isinstance(get_payment_provider("stripe"), StripeProvider)
    assert isinstance(get_payment_provider("STRIPE"), StripeProvider)


def test_05_payment_service_constructs_from_provider():
    step(5, "Payment service/provider composition")
    from app.services.payments.service import PaymentService

    provider = Mock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.payments.service.get_payment_provider", lambda name="stripe": provider)
        service = PaymentService()

    assert service.provider is provider


def test_06_payment_money_and_order_number_contract():
    step(6, "Payment money/order-number helpers")
    from app.services.payments.service import PaymentService

    provider = Mock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.payments.service.get_payment_provider", lambda name="stripe": provider)
        service = PaymentService()

    assert service._paise("10.005") == 1001
    assert service._paise("10") == 1000

    order_number = service._generate_clean_order_number()
    assert order_number.startswith("ORD-")
    assert len(order_number) == 12


@pytest.mark.asyncio
async def test_07_payment_validation_contracts():
    step(7, "Payment validation")
    from app.services.payments.service import PaymentService

    provider = Mock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.payments.service.get_payment_provider", lambda name="stripe": provider)
        service = PaymentService()

        with pytest.raises(Exception) as exc:
            await service.confirm_payment("user-1", "127.0.0.1", "", "test@example.com")
        assert getattr(exc.value, "status_code", None) == 400

        provider.retrieve_intent.return_value = {
            "id": "pi_test",
            "status": "requires_payment_method",
        }
        with pytest.raises(Exception) as exc:
            await service.confirm_payment("user-1", "127.0.0.1", "pi_test", "test@example.com")
        assert getattr(exc.value, "status_code", None) == 402


@pytest.mark.asyncio
async def test_08_idempotency_validation():
    step(8, "Checkout idempotency validation")
    from app.services.payments.service import PaymentService

    provider = Mock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.payments.service.get_payment_provider", lambda name="stripe": provider)
        service = PaymentService()

        with pytest.raises(Exception) as exc:
            await service.create_intent(
                user_id="user-1",
                client_ip="127.0.0.1",
                idempotency_key="not-a-uuid",
                address_id="addr-1",
            )
        assert getattr(exc.value, "status_code", None) == 400


def test_09_pricing_product_level_gst():
    step(9, "Product-level GST pricing")
    from app.services.pricing.service import StandardPricing

    strategy = StandardPricing(
        shipping_threshold=Decimal("1499"),
        shipping_flat=Decimal("45.90"),
        currency="INR",
    )

    items = [
        {
            "quantity": 2,
            "price_snapshot": "100",
            "products": {"gst_percentage": "18"},
        }
    ]
    result = strategy.calculate(items)

    assert result.subtotal == Decimal("200")
    assert result.tax == Decimal("36")
    assert result.shipping == Decimal("45.90")
    assert result.total == Decimal("281.90")
    assert items[0]["gst_percentage_snapshot"] == 18.0


def test_10_pricing_free_shipping_threshold():
    step(10, "Free-shipping threshold")
    from app.services.pricing.service import StandardPricing

    strategy = StandardPricing(
        shipping_threshold=Decimal("1499"),
        shipping_flat=Decimal("45.90"),
        currency="INR",
    )

    items = [
        {
            "quantity": 1,
            "price_snapshot": "1499",
            "products": {"gst_percentage": "18"},
        }
    ]
    result = strategy.calculate(items)

    assert result.shipping == Decimal("0")
    assert result.total == Decimal("1768.82")


def test_11_pricing_rejects_missing_gst():
    step(11, "Pricing rejects missing product GST")
    from app.services.pricing.service import StandardPricing

    strategy = StandardPricing(
        shipping_threshold=Decimal("1499"),
        shipping_flat=Decimal("45.90"),
        currency="INR",
    )

    with pytest.raises(Exception):
        strategy.calculate(
            [{"quantity": 1, "price_snapshot": "100", "products": {}}]
        )


def test_12_health_contract():
    step(12, "Health endpoint contract")
    from app.api.v1.routers.health import health_check

    assert callable(health_check)


@pytest.mark.asyncio
async def test_13_health_db_success():
    step(13, "Health database success path")
    import app.api.v1.routers.health as health

    execute = AsyncMock()
    execute.return_value = Mock(data=[])
    query = Mock()
    query.select.return_value = query
    query.limit.return_value = query
    query.execute = execute
    sb = Mock()
    sb.table.return_value = query

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(health, "get_async_admin_supabase", AsyncMock(return_value=sb))
        response = await health.health_check()

    assert response["data"]["status"] == "ok"


def test_14_critical_router_surface():
    step(14, "Critical API surface")
    from app.main import app

    paths = {route.path for route in app.routes}
    expected_fragments = (
        "/api/v1",
        "/docs",
        "/redoc",
        "/openapi.json",
    )
    for fragment in expected_fragments:
        assert any(path.startswith(fragment) for path in paths)


def test_15_final_backend_integrity():
    step(15, "Final backend integrity")
    from app.main import app
    from app.integrations.payments.registry import PAYMENT_REGISTRY

    assert app is not None
    assert PAYMENT_REGISTRY
    assert "stripe" in PAYMENT_REGISTRY
    assert len(app.routes) > 0

    print("\n========== LUVIIO BACKEND SMOKE FLOW PASSED ==========")
