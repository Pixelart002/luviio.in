from unittest.mock import AsyncMock, patch

import pytest

from app.domains.shipping.service import ShippingService

SHIPPING_FLAT = "flat"
SHIPPING_FREE_THRESHOLD = "free_threshold"
SHIPPING_PER_ITEM = "per_item"
SHIPPING_WEIGHT = "weight"


def _settings(enabled=True):
    settings = AsyncMock()
    values = {
        "shipping_enabled": enabled,
        "free_shipping_threshold": "1499",
        "flat_shipping_rate": "45.90",
    }
    settings.fetch_by_key = AsyncMock(side_effect=lambda key: values[key])
    return settings


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
    settings = _settings()
    with patch("app.domains.shipping.service.SettingsCoreEngine", return_value=settings):
        result = await service.compute_rate(200, 1, 0, "method-1")

    assert result["shipping_cost"] == 10
    assert result["applied_type"] == SHIPPING_FLAT


@pytest.mark.asyncio
async def test_compute_rate_uses_canonical_flat_shipping_rate():
    service = ShippingService()
    service.repo = AsyncMock()
    service.repo.list_active_methods = AsyncMock(return_value=[{
        "type": SHIPPING_FLAT,
        "base_rate": 45.90,
        "id": "method-1",
        "is_active": True,
    }])
    settings = _settings()
    with patch("app.domains.shipping.service.SettingsCoreEngine", return_value=settings):
        result = await service.compute_rate(1000, 1, 0)

    assert result["shipping_cost"] == 45.90
    assert result["free_shipping_threshold"] == 1499.0
    assert result["applied_type"] == "settings_default"
    assert result["method_id"] == "method-1"
    settings.fetch_by_key.assert_any_await("shipping_enabled")
    settings.fetch_by_key.assert_any_await("flat_shipping_rate")
    settings.fetch_by_key.assert_any_await("free_shipping_threshold")


@pytest.mark.asyncio
@pytest.mark.parametrize("subtotal,expected", [(1498.99, 45.90), (1499.0, 0.0), (1800.0, 0.0)])
async def test_threshold_boundary(subtotal, expected):
    service = ShippingService()
    service.repo = AsyncMock()
    service.repo.list_active_methods = AsyncMock(return_value=[{"id": "method-1", "is_active": True}])
    settings = _settings()
    with patch("app.domains.shipping.service.SettingsCoreEngine", return_value=settings):
        result = await service.compute_rate(subtotal)
    assert result["shipping_cost"] == expected


@pytest.mark.asyncio
async def test_shipping_disabled_returns_zero():
    service = ShippingService()
    service.repo = AsyncMock()
    service.repo.list_active_methods = AsyncMock(return_value=[{"id": "method-1", "is_active": True}])
    settings = _settings(enabled=False)
    with patch("app.domains.shipping.service.SettingsCoreEngine", return_value=settings):
        result = await service.compute_rate(1000)
    assert result["shipping_cost"] == 0.0
    assert result["applied_type"] == "disabled"


@pytest.mark.asyncio
async def test_compute_rate_rejects_zero_items():
    service = ShippingService()
    service.repo = AsyncMock()
    with pytest.raises(Exception):
        await service.compute_rate(1000, 0)
    service.repo.list_active_methods.assert_not_awaited()
