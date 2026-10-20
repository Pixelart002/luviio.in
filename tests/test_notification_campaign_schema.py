"""Contract tests for administrator-configured Web Push campaigns."""
import pytest
from pydantic import ValidationError

from app.domains.notifications.schemas import BatchNotificationRequest


def test_legacy_batch_notification_defaults_remain_compatible():
    payload = BatchNotificationRequest(body="A standard notification.")

    assert payload.user_ids is None
    assert payload.url == "/"
    assert payload.icon == "/icon-192.png"
    assert payload.actions == []
    assert payload.require_interaction is False


def test_rich_campaign_accepts_same_site_product_link_and_actions():
    payload = BatchNotificationRequest(
        title="New Luviio offer",
        body="Explore the new floor drainer.",
        url="/products/floor-drainer-square-ring",
        icon="/icon-192.png",
        badge="/icon-192.png",
        image="/assets/offer.webp",
        tag="festive-sale",
        require_interaction=True,
        renotify=True,
        actions=[
            {"title": "Shop now", "action": "/offers"},
            {"title": "Product", "action": "/products/floor-drainer-square-ring"},
        ],
    )

    assert payload.image == "/assets/offer.webp"
    assert len(payload.actions) == 2
    assert payload.actions[0].action == "/offers"


@pytest.mark.parametrize(
    "field,value",
    [
        ("url", "https://example.com/phishing"),
        ("url", "//example.com"),
        ("icon", "javascript:alert(1)"),
        ("image", "https://example.com/banner.webp"),
        ("badge", "\\evil.example/path"),
    ],
)
def test_notification_assets_and_click_paths_must_be_same_site(field, value):
    with pytest.raises(ValidationError):
        BatchNotificationRequest(body="Offer", **{field: value})


def test_luviio_hosted_notification_assets_are_accepted(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SB_URL", "https://luviio-test.supabase.co")
    asset_url = "https://luviio-test.supabase.co/storage/v1/object/public/product-images/notifications/campaign.webp"
    payload = BatchNotificationRequest(body="Offer", icon=asset_url, badge=asset_url, image=asset_url)

    assert payload.icon == asset_url
    assert payload.badge == asset_url
    assert payload.image == asset_url


def test_notification_asset_must_belong_to_configured_supabase_project(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SB_URL", "https://luviio-test.supabase.co")
    with pytest.raises(ValidationError):
        BatchNotificationRequest(
            body="Offer",
            icon="https://other-project.supabase.co/storage/v1/object/public/product-images/notifications/evil.webp",
        )


def test_external_notification_action_is_rejected():
    with pytest.raises(ValidationError):
        BatchNotificationRequest(
            body="Offer",
            actions=[{"title": "Open", "action": "https://example.com"}],
        )


def test_more_than_two_notification_actions_are_rejected():
    with pytest.raises(ValidationError):
        BatchNotificationRequest(
            body="Offer",
            actions=[
                {"title": "One", "action": "/one"},
                {"title": "Two", "action": "/two"},
                {"title": "Three", "action": "/three"},
            ],
        )
