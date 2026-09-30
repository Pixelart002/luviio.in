import pytest

from app.integrations.shipping.rapidshyp import RapidShypProvider
from app.integrations.shipping.registry import get_shipping_provider


def test_rapidshyp_provider_uses_api_key_and_default_endpoint(monkeypatch):
    monkeypatch.setenv("RAPIDSHYP_TOKEN", "test-token")
    monkeypatch.delenv("RAPIDSHYP_BASE_URL", raising=False)

    provider = RapidShypProvider()

    assert provider.base_url == "https://api.rapidshyp.com/rapidshyp/apis/v1"
    assert provider.token == "test-token"
    assert provider.supports_label is True
    assert provider.supports_manifest is False
    assert provider.supports_invoice is False


def test_rapidshyp_provider_allows_explicit_base_url(monkeypatch):
    monkeypatch.setenv("RAPIDSHYP_TOKEN", "test-token")
    monkeypatch.setenv("RAPIDSHYP_BASE_URL", "https://rapid.example.test/api/v1")

    provider = RapidShypProvider()

    assert provider.base_url == "https://rapid.example.test/api/v1"


def test_rapidshyp_is_registered(monkeypatch):
    monkeypatch.setenv("RAPIDSHYP_TOKEN", "test-token")
    get_shipping_provider.cache_clear()

    provider = get_shipping_provider("rapidshyp")

    assert provider.key == "rapidshyp"


@pytest.mark.asyncio
async def test_rapidshyp_serviceability_payload(monkeypatch):
    monkeypatch.setenv("RAPIDSHYP_TOKEN", "test-token")
    provider = RapidShypProvider()

    captured = {}

    async def fake_request(method, path, *, json=None):
        captured.update({"method": method, "path": path, "json": json})
        return {
            "status": True,
            "serviceable_courier_list": [
                {
                    "courier_code": "6001",
                    "courier_name": "Example Courier",
                    "total_freight": 42.5,
                }
            ],
        }

    monkeypatch.setattr(provider, "_request", fake_request)

    response = await provider.serviceability(
        pickup_postcode="110001",
        delivery_postcode="110002",
        weight_kg=0.5,
        cod=True,
        declared_value=999,
    )

    assert captured == {
        "method": "POST",
        "path": "/serviceability_check",
        "json": {
            "Pickup_pincode": "110001",
            "Delivery_pincode": "110002",
            "cod": True,
            "total_order_value": 999.0,
            "weight": 0.5,
        },
    }
    assert response["serviceable_courier_list"][0]["courier_code"] == "6001"
