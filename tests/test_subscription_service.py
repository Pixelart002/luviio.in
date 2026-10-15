from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.domains.subscriptions.service import SubscriptionService


@pytest.mark.asyncio
async def test_get_tier_for_user_active_sub():
    service = SubscriptionService()
    service.repo = AsyncMock()
    service.repo.get_active_for_user = AsyncMock(return_value={
        "tier": "premium",
        "plan_id": "plan-1",
        "plan_name": "Premium Plan",
        "ends_at": "2026-12-31T23:59:59",
    })
    result = await service.get_tier_for_user("user-1")
    assert result["tier"] == "premium"
    assert result["plan_id"] == "plan-1"
    assert result["perks"]["free_shipping"] is True


@pytest.mark.asyncio
async def test_get_tier_for_user_fallback():
    service = SubscriptionService()
    service.repo = AsyncMock()
    service.repo.get_active_for_user = AsyncMock(return_value=None)
    result = await service.get_tier_for_user("user-1")
    assert result["tier"] == "free"
    assert result["perks"]["free_shipping"] is False


@pytest.mark.asyncio
async def test_get_tier_for_user_user_tier_fallback():
    service = SubscriptionService()
    service.repo = AsyncMock()
    service.repo.get_active_for_user = AsyncMock(return_value=None)
    result = await service.get_tier_for_user("user-1", user={"tier": "premium"})
    assert result["tier"] == "premium"
    assert result["perks"]["free_shipping"] is True


@pytest.mark.asyncio
async def test_subscribe():
    service = SubscriptionService()
    service.repo = AsyncMock()
    service.repo.get_active_for_user = AsyncMock(return_value=None)
    service.repo.get_plan = AsyncMock(return_value={"id": "plan-1", "tier": "free", "price_inr": 0, "duration_days": 30})
    service.repo.upsert_subscription = AsyncMock(
        return_value={"id": "sub-1", "status": "active", "plan_id": "plan-1"})
    result = await service.subscribe("user-1", "plan-1")
    assert result["status"] == "active"
    assert result["plan_id"] == "plan-1"


@pytest.mark.asyncio
async def test_paid_subscribe_requires_payment():
    service = SubscriptionService()
    service.repo = AsyncMock()
    service.repo.get_plan = AsyncMock(return_value={
        "id": "plan-paid", "tier": "premium", "price_inr": 199, "duration_days": 30, "is_active": True
    })
    with pytest.raises(HTTPException) as exc:
        await service.subscribe("user-1", "plan-paid")
    assert exc.value.status_code == 402
    service.repo.upsert_subscription.assert_not_called()
