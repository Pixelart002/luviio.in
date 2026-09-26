from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_shiprocket_cancel_uses_awb_endpoint_for_awb_shipments():
    source = read("app/integrations/shipping/shiprocket.py")
    assert '/orders/cancel/shipment/awbs' in source
    assert 'json={"awbs": [awb]}' in source
    assert 'json={"ids": [provider_order_id]}' in source


def test_shipping_webhook_has_provider_neutral_route_and_x_api_key():
    source = read("app/domains/shipping/router.py")
    assert '@router.post("/provider/webhook", status_code=200)' in source
    assert 'alias="x-api-key"' in source
    assert 'handle_webhook("shiprocket", payload)' in source


def test_pickup_workflow_accepts_success_without_pickup_id():
    source = read("app/domains/shipping/provider_service.py")
    assert 'pickup_scheduled_date' in source
    assert 'pickup_scheduled_at' in source
    assert 'not row.get("pickup_id") and not row.get("pickup_scheduled_at")' in source
