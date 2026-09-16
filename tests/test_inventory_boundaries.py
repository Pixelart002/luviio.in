from unittest.mock import AsyncMock

import pytest

from app.domains.inventory.service import InventoryService


@pytest.mark.asyncio
async def test_commit_reservation_requires_verified_currency():
    service = InventoryService()
    service.repo.settle_order_transaction = AsyncMock()

    with pytest.raises(ValueError, match="Stripe currency is required"):
        await service.commit_reservation("order-1", "pi-1", 100, "user-1")

    service.repo.settle_order_transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_commit_reservation_forwards_verified_currency():
    service = InventoryService()
    service.repo.settle_order_transaction = AsyncMock(return_value="SETTLED")

    result = await service.commit_reservation(
        "order-1",
        "pi-1",
        100,
        "user-1",
        payment_method="card",
        stripe_currency="inr",
    )

    assert result == "SETTLED"
    service.repo.settle_order_transaction.assert_awaited_once_with(
        order_id="order-1",
        pi_id="pi-1",
        amount=100,
        user_id="user-1",
        payment_method="card",
        stripe_currency="inr",
    )


@pytest.mark.asyncio
async def test_check_availability_rejects_zero_quantity():
    service = InventoryService()
    service.repo.get_product_stock_status = AsyncMock()

    with pytest.raises(ValueError, match="positive integer"):
        await service.check_availability("product-1", 0)

    service.repo.get_product_stock_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_adjust_stock_rejects_zero_delta():
    service = InventoryService()
    service.repo.admin_adjust_stock = AsyncMock()

    with pytest.raises(ValueError, match="non-zero integer"):
        await service.adjust_stock("product-1", 0, "test")

    service.repo.admin_adjust_stock.assert_not_awaited()
