# ruff: noqa: I001 - keep test imports explicit for module-path monkeypatching.
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.cart.repository import AsyncCartRepository
from app.domains.cart.service import CartService


PRICING_CONFIG = {
    "tax_enabled": False,
    "shipping_enabled": False,
    "currency": "INR",
    "shipping_flat": 0,
    "shipping_threshold": 1499,
}


@pytest.mark.asyncio
async def test_get_cart_uses_one_snapshot_and_reuses_all_read_data():
    service = CartService()
    snapshot = {
        "cart": {"id": "cart-1"},
        "pricing_config": PRICING_CONFIG,
        "items": [{"id": "item-1", "quantity": 1}],
    }
    service.repo = SimpleNamespace(get_cart_snapshot=AsyncMock(return_value=snapshot))
    service._calculate_cart_pricing = AsyncMock(return_value={"items": []})

    result = await service.get_cart("user-1")

    assert result == {"items": []}
    service.repo.get_cart_snapshot.assert_awaited_once_with("user-1")
    service._calculate_cart_pricing.assert_awaited_once_with(
        "cart-1",
        pricing_config=PRICING_CONFIG,
        raw_items=snapshot["items"],
    )


@pytest.mark.asyncio
async def test_snapshot_rpc_is_one_supabase_call(monkeypatch):
    snapshot = {
        "cart": {"id": "cart-1"},
        "pricing_config": PRICING_CONFIG,
        "items": [],
    }
    calls = []

    class FakeRpc:
        async def execute(self):
            return SimpleNamespace(data=snapshot)

    class FakeAdminClient:
        def rpc(self, function_name, params):
            calls.append((function_name, params))
            return FakeRpc()

    monkeypatch.setattr(
        "app.domains.cart.repository.get_async_admin_supabase",
        AsyncMock(return_value=FakeAdminClient()),
    )

    result = await AsyncCartRepository().get_cart_snapshot("user-1")

    assert result == snapshot
    assert calls == [("get_cart_snapshot", {"p_user_id": "user-1"})]


@pytest.mark.asyncio
async def test_pricing_does_not_fetch_again_when_snapshot_is_supplied():
    service = CartService()
    service.repo = SimpleNamespace(
        get_pricing_config=AsyncMock(side_effect=AssertionError("unexpected config read")),
        get_cart_items_with_products=AsyncMock(side_effect=AssertionError("unexpected item read")),
    )

    result = await service._calculate_cart_pricing(
        "cart-1",
        pricing_config=PRICING_CONFIG,
        raw_items=[],
    )

    assert result["items"] == []
    assert result["item_count"] == 0
    service.repo.get_pricing_config.assert_not_awaited()
    service.repo.get_cart_items_with_products.assert_not_awaited()
