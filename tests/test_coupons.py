from unittest.mock import AsyncMock, patch

import pytest

from app.domains.coupons.service import CouponService


def test_compute_discount():
    coupon = {
        "type": "percent", "value": 10, "max_discount": 10,
        "min_order_amount": 0, "is_active": True,
        "valid_from": None, "valid_until": None,
        "usage_limit": None, "per_user_limit": 1, "used_count": 0,
    }
    assert CouponService._compute_discount(coupon, 100) == 10


def test_compute_discount_capped():
    coupon = {
        "type": "percent", "value": 10, "max_discount": 5,
        "min_order_amount": 0, "is_active": True,
        "valid_from": None, "valid_until": None,
        "usage_limit": None, "per_user_limit": 1, "used_count": 0,
    }
    assert CouponService._compute_discount(coupon, 100) == 5


def test_compute_discount_fixed_capped():
    coupon = {
        "type": "fixed", "value": 20, "max_discount": 10,
        "min_order_amount": 0, "is_active": True,
        "valid_from": None, "valid_until": None,
        "usage_limit": None, "per_user_limit": 1, "used_count": 0,
    }
    assert CouponService._compute_discount(coupon, 100) == 10


def test_normalize_code():
    assert CouponService._normalize_code("  luviio  ") == "LUVIIO"


def test_normalize_empty_code_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        CouponService._normalize_code("   ")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_resolve_discount_for_checkout_normalizes_code():
    coupon_service = CouponService()
    coupon_service.repo = AsyncMock()
    coupon_service.repo.get_by_code = AsyncMock(return_value={
        "id": "coupon-1", "code": "TEST10", "type": "percent",
        "value": 10, "max_discount": 10, "min_order_amount": 0,
        "is_active": True, "valid_from": None, "valid_until": None,
        "usage_limit": None, "per_user_limit": 1, "used_count": 0,
    })
    coupon_service.repo.redemptions_for_user = AsyncMock(return_value=0)

    with patch("app.domains.coupons.service.assert_action_enabled", new=AsyncMock()):
        resolved = await coupon_service.resolve_discount_for_checkout("  test10 ", 100, "user-1")

    coupon_service.repo.get_by_code.assert_awaited_once_with("TEST10")
    assert resolved == {"discount": 10, "coupon_id": "coupon-1", "code": "TEST10"}


@pytest.mark.asyncio
async def test_resolve_discount_for_checkout_inactive():
    from fastapi import HTTPException

    coupon_service = CouponService()
    coupon_service.repo = AsyncMock()
    coupon_service.repo.get_by_code = AsyncMock(return_value={
        "id": "coupon-1", "code": "TEST10", "type": "percent",
        "value": 10, "max_discount": 10, "min_order_amount": 0,
        "is_active": False, "valid_from": None, "valid_until": None,
        "usage_limit": None, "per_user_limit": 1, "used_count": 0,
    })
    coupon_service.repo.redemptions_for_user = AsyncMock(return_value=0)

    with patch("app.domains.coupons.service.assert_action_enabled", new=AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await coupon_service.resolve_discount_for_checkout("TEST10", 100, "user-1")
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_rejects_coupon_code_collision():
    coupon_service = CouponService()
    coupon_service.repo = AsyncMock()
    coupon_service.repo.get_by_id = AsyncMock(return_value={"id": "coupon-1", "code": "OLD"})
    coupon_service.repo.get_by_code = AsyncMock(return_value={"id": "coupon-2", "code": "NEW"})

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await coupon_service.update("coupon-1", {"code": " new "})

    assert exc.value.status_code == 400
    coupon_service.repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_allows_same_normalized_coupon_code():
    coupon_service = CouponService()
    coupon_service.repo = AsyncMock()
    coupon_service.repo.get_by_id = AsyncMock(return_value={"id": "coupon-1", "code": "TEST10"})
    coupon_service.repo.get_by_code = AsyncMock(return_value={"id": "coupon-1", "code": "TEST10"})
    coupon_service.repo.update = AsyncMock(return_value={
        "id": "coupon-1", "code": "TEST10", "type": "percent", "value": 10,
    })

    updated = await coupon_service.update("coupon-1", {"code": " test10 "})

    assert updated["code"] == "TEST10"
    coupon_service.repo.update.assert_awaited_once_with("coupon-1", {"code": "TEST10"})
