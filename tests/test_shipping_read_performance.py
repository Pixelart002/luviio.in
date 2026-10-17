from unittest.mock import AsyncMock

import pytest

from app.domains.shipping.provider_service import ShippingProviderService


@pytest.mark.asyncio
async def test_shipment_read_skips_repeat_order_lookup_and_write_when_in_sync():
    service = ShippingProviderService()
    service.repo = AsyncMock()
    shipment = {
        "id": "shipment-1",
        "order_id": "order-1",
        "provider_key": "manual",
        "status": "manual_pending",
        "workflow_status": "created",
    }
    service.repo.get_by_order.return_value = shipment

    result = await service.get_for_order("order-1", order_status="pending")

    assert result == shipment
    service.repo.get_by_order.assert_awaited_once_with("order-1", "manual")
    service.repo.update.assert_not_awaited()
