import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.cart.service import CartService


@pytest.mark.asyncio
async def test_get_cart_starts_cart_and_pricing_reads_concurrently():
    service = CartService()
    started = set()
    both_started = asyncio.Event()
    config = {"tax_enabled": False}

    async def rendezvous(name, value):
        started.add(name)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        return value

    service.repo = SimpleNamespace(
        get_or_create_cart=lambda user_id: rendezvous("cart", {"id": "cart-1"}),
        get_pricing_config=lambda: rendezvous("pricing", config),
    )
    service._calculate_cart_pricing = AsyncMock(return_value={"items": []})

    result = await service.get_cart("user-1")

    assert result == {"items": []}
    assert started == {"cart", "pricing"}
    service._calculate_cart_pricing.assert_awaited_once_with(
        "cart-1", pricing_config=config
    )
