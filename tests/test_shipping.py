from unittest.mock import AsyncMock, patch

import pytest

from app.domains.shipping.service import ShippingService

SHIPPING_FLAT = "flat"
SHIPPING_FREE_THRESHOLD = "free_threshold"
SHIPPING_PER_ITEM = "per_item"
SHIPPING_WEIGHT = "weight"


@pytest.mark.parametrize("mtype,base_rate,per_item_rate,item_count,expected", [
    (SHIPPING_FLAT, 10, 0, 1, 10),
    (SHIPPING_PER_ITEM, 5, 3, 2, 5 + 6),
    (SHIPPING_WEIGHT, 5, 0, 0, 5 + 2 * 1),
    (SHIPPING_FREE_THRESHOLD, 10, 0, 1, 0),
])
def test_compute_method_rate(mtype, base_rate, per_item_rate, item_count, expected):
    method = {
        "type": mtype,
        "base_rate": base_rate,
        "per_item_rate": per_item_rate,
        "weight_rate": 2,
        "threshold": 100,
        "id": "method-1",
        "is_active": True,
    }
    assert ShippingService._compute_method_rate(method, 200, item_count, 1) == {
        "shipping_cost": expected,
        "method": method,
        "method_id": "method-1",
        "applied_type": mtype,
    }


@pytest.mark.asyncio
async def test_compute_rate_method_id():
    service = ShippingService()
    service.repo = AsyncMock()
    service.repo.get_by_id = AsyncMock(return_value={
        "type": SHIPPING_FLAT,
        "base_rate": 10,
        "id": "method-1",
        "is_active": True,
    })
    result = await service.compute_rate(200, 1, 0, "method-1")
    assert result["shipping_cost"] == 10
    assert result["applied_type"] == SHIPPING_FLAT


@pytest.mark.asyncio
async def test_compute_rate_no_method_id():
    service = ShippingService()
    service.repo = AsyncMock()
    service.repo.list_active_methods = AsyncMock(return_value=[{
        "type": SHIPPING_FLAT,
        "base_rate": 10,
        "id": "method-1",
        "is_active": True,
    }])
    settings = AsyncMock()
    settings.fetch_by_key = AsyncMock(
        side_effect=lambda key: {"free_shipping_threshold": "100",
                                 "standard_shipping_cost": "45.90"}[key])
    with patch("app.domains.shipping.service.SettingsCoreEngine", return_value=settings):
        result = await service.compute_rate(200, 1, 0)
    assert result["shipping_cost"] == 0.0       # 200 >= threshold(100) -> free
    assert result["applied_type"] == "settings_default"
    assert result["method_id"] == "method-1"
