"""
Subscriptions Domain — Package
===============================
Path: app/domains/subscriptions/__init__.py

Self-contained domain (clean approach):
  * tier_registry.py  -> SSOT: free/premium/platinum perks + normalize
  * schemas.py        -> subscription_plan / membership request DTOs
  * policy.py         -> tier + plan access rules
  * repository.py     -> subscription_plans + user_subscriptions tables
  * service.py        -> effective-tier resolution, plan CRUD, subscribe
  * router.py         -> /subscriptions routes

OTHER DOMAINS consume the tier via `SubscriptionService.get_tier_for_user`
(or directly `get_tier_perks` / `get_pricing_for_user` in pricing+orders).
"""
from app.domains.subscriptions.tier_registry import (
    TIERS, TIER_ORDER, TierPerks, get_tier_perks, is_tier_at_least,
    normalize_tier, render_tier, tier_rank,
)

__all__ = [
    "TIERS", "TIER_ORDER", "TierPerks",
    "get_tier_perks", "is_tier_at_least", "normalize_tier",
    "render_tier", "tier_rank",
]
