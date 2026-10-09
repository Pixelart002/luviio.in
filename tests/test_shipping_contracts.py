from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_checkout_shipping_is_manual_and_has_no_external_provider():
    source = read("app/domains/shipping/provider_service.py")
    assert 'MANUAL_PROVIDER = "manual"' in source
    assert '"shipping_mode": MANUAL_PROVIDER' in source
    assert "External shipping providers are disabled" in source


def test_shipping_webhook_has_provider_neutral_route_and_x_api_key():
    source = read("app/domains/shipping/router.py")
    assert '@router.post("/provider/webhook", status_code=200)' in source
    assert 'alias="x-api-key"' in source
    assert 'handle_webhook("manual", payload)' in source


def test_external_pickup_workflow_is_disabled_in_manual_shipping_mode():
    source = read("app/domains/shipping/provider_service.py")
    assert 'async def schedule_pickup(self, shipment_id: str)' in source
    assert 'return await self._manual_operation("Provider pickup scheduling")' in source
    assert "External shipping webhooks are disabled. Shipping is handled manually." in source
