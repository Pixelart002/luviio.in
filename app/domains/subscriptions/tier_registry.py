"""
Subscription Tier Registry (SSOT)
=================================
Path: app/domains/subscriptions/tier_registry.py

⚠️ SEPARATION OF CONCERNS:
  * PRODUCT PRICING (wo number jis par product bech rahe ho) `products.price` +
    `app.domains.pricing` mein hai — GST, shipping, totals. Ye UNCHANGED hai
    aur is file se independent.
  * SUBSCRIPTION PRICING / PERKS yahan hain. Ek tier kabhi product ki price
    nahi badalta; wo sirf checkout ke PERKS deta hai — free shipping, member
    discount, aur premium/platinum-gated products tak access.

Tiers (bottom → top): free → premium → platinum.
`get_pricing_for_user` wrapper `perks.free_shipping` + `perks.discount_percent`
consume karta hai — ye product price ko kabhi touch nahi karta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class TierPerks:
    free_shipping: bool = False
    discount_percent: Decimal = Decimal("0")   # member discount on order (product price untouched)
    can_access_premium: bool = False
    can_access_platinum: bool = False
    extra_actions: tuple[str, ...] = field(default_factory=tuple)


TIER_ORDER = ("free", "premium", "platinum")

TIERS: dict[str, TierPerks] = {
    "free": TierPerks(free_shipping=False, discount_percent=Decimal("0"),
                      can_access_premium=False, can_access_platinum=False),
    "premium": TierPerks(free_shipping=True, discount_percent=Decimal("5"),
                         can_access_premium=True, can_access_platinum=False),
    "platinum": TierPerks(free_shipping=True, discount_percent=Decimal("10"),
                          can_access_premium=True, can_access_platinum=True,
                          extra_actions=("priority_support", "early_access")),
}


def normalize_tier(tier: Any) -> str:
    """Legacy tier names (vip/prime/normal) ko naye 3-tier system par map karta hai."""
    t = str(tier or "free").lower().strip()
    if t in TIERS:
        return t
    legacy = {
        "normal": "free", "basic": "free",
        "vip": "platinum", "prime": "platinum",
        "gold": "premium", "silver": "premium",
    }
    return legacy.get(t, "free")


def get_tier_perks(tier: Any) -> TierPerks:
    return TIERS[normalize_tier(tier)]


def tier_rank(tier: Any) -> int:
    return TIER_ORDER.index(normalize_tier(tier))


def is_tier_at_least(tier: Any, minimum: str) -> bool:
    return tier_rank(tier) >= tier_rank(minimum)


def all_tiers_public() -> list[dict[str, Any]]:
    out = []
    for name in TIER_ORDER:
        out.append(render_tier(name))
    return out


def render_tier(tier: Any) -> dict[str, Any]:
    """Tier + perks ko ek flat dict me render karta hai (admin/show response)."""
    name = normalize_tier(tier)
    perks = TIERS[name]
    return {
        "tier": name,
        "label": name.capitalize(),
        "free_shipping": perks.free_shipping,
        "discount_percent": float(perks.discount_percent),
        "can_access_premium": perks.can_access_premium,
        "can_access_platinum": perks.can_access_platinum,
        "extra_actions": list(perks.extra_actions),
    }
