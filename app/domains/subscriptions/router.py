"""
Subscription Domain — Router
============================
Path: app/domains/subscriptions/router.py
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.dependencies import get_user_id_strict, require_permission
from app.domains.subscriptions.schemas import SubscribeRequest, SubscriptionCancelRequest, SubscriptionPlanCreate, SubscriptionPlanUpdate, TierPublic
from app.domains.subscriptions.service import SubscriptionService
from app.permissions.subscriptions import SubscriptionPermissions

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
service = SubscriptionService()


@router.get("/plans", response_model=list[dict[str, Any]])
async def list_plans(active_only: bool = True, _ = Depends(require_permission(SubscriptionPermissions.READ_PLANS))):
    return await service.list_plans(active_only=active_only)


@router.get("/plans/public", response_model=list[TierPublic])
async def public_tiers(_ = Depends(require_permission(SubscriptionPermissions.READ_PLANS))):
    return await service.public_tiers()


@router.post("/plans", response_model=dict[str, Any])
async def create_plan(payload: SubscriptionPlanCreate, _ = Depends(require_permission(SubscriptionPermissions.MANAGE))):
    return await service.create_plan(payload.model_dump(exclude_unset=True))


@router.put("/plans/{plan_id}", response_model=dict[str, Any])
async def update_plan(plan_id: str, payload: SubscriptionPlanUpdate, _ = Depends(require_permission(SubscriptionPermissions.MANAGE))):
    return await service.update_plan(plan_id, payload.model_dump(exclude_unset=True))


@router.post("/subscribe", response_model=dict[str, Any])
async def subscribe(payload: SubscribeRequest, user_id: str = Depends(get_user_id_strict), _ = Depends(require_permission(SubscriptionPermissions.SUBSCRIBE))):
    return await service.subscribe(user_id, payload.plan_id)


@router.post("/cancel", response_model=dict[str, Any])
async def cancel_subscription(payload: SubscriptionCancelRequest, user_id: str = Depends(get_user_id_strict), _ = Depends(require_permission(SubscriptionPermissions.SUBSCRIBE))):
    return await service.cancel(user_id, payload.reason)


@router.get("/me", response_model=dict[str, Any])
async def my_subscription(user_id: str = Depends(get_user_id_strict), _ = Depends(require_permission(SubscriptionPermissions.READ_MINE))):
    return await service.get_tier_for_user(user_id)


@router.get("/reminders", response_model=list[dict[str, Any]])
async def reminders(user_id: str = Depends(get_user_id_strict), _ = Depends(require_permission(SubscriptionPermissions.READ_MINE))):
    return await service.get_reminders(user_id)


@router.post("/reminders/{reminder_id}/dismiss", response_model=dict[str, bool])
async def dismiss_reminder(reminder_id: str, user_id: str = Depends(get_user_id_strict), _ = Depends(require_permission(SubscriptionPermissions.READ_MINE))):
    await service.dismiss_reminder(user_id, reminder_id)
    return {"dismissed": True}
