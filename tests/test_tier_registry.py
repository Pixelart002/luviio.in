from app.domains.subscriptions.tier_registry import (
    normalize_tier,
    get_tier_perks,
    tier_rank,
    is_tier_at_least,
    all_tiers_public,
    render_tier,
)


def test_normalize_tier_legacy():
    assert normalize_tier("vip") == "platinum"
    assert normalize_tier("prime") == "platinum"
    assert normalize_tier("gold") == "premium"
    assert normalize_tier("silver") == "premium"
    assert normalize_tier("normal") == "free"
    assert normalize_tier("basic") == "free"
    assert normalize_tier("foo") == "free"
    assert normalize_tier(None) == "free"
    assert normalize_tier("premium") == "premium"


def test_get_tier_perks():
    assert get_tier_perks("free").free_shipping is False
    assert get_tier_perks("premium").discount_percent == 5
    assert get_tier_perks("platinum").discount_percent == 10
    assert get_tier_perks("platinum").can_access_premium is True
    assert get_tier_perks("platinum").can_access_platinum is True


def test_tier_rank():
    assert tier_rank("free") == 0
    assert tier_rank("premium") == 1
    assert tier_rank("platinum") == 2


def test_is_tier_at_least():
    assert is_tier_at_least("free", "free")
    assert is_tier_at_least("premium", "free")
    assert is_tier_at_least("premium", "premium")
    assert is_tier_at_least("platinum", "premium") is True
    assert is_tier_at_least("platinum", "platinum")


def test_render_tier():
    assert render_tier("free") == {
        "tier": "free",
        "label": "Free",
        "free_shipping": False,
        "discount_percent": 0.0,
        "can_access_premium": False,
        "can_access_platinum": False,
        "extra_actions": [],
    }


def test_all_tiers_public():
    tiers = all_tiers_public()
    assert len(tiers) == 3
    assert any(t["tier"] == "free" for t in tiers)
    assert any(t["tier"] == "premium" for t in tiers)
    assert any(t["tier"] == "platinum" for t in tiers)
