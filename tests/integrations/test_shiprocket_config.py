from app.integrations.shipping.shiprocket import ShiprocketProvider


def test_shiprocket_sandbox_uses_dedicated_hosts(monkeypatch):
    monkeypatch.setenv("SHIPROCKET_ENV", "sandbox")
    for key in (
        "SHIPROCKET_BASE_URL",
        "SHIPROCKET_SERVICEABILITY_BASE_URL",
        "SHIPROCKET_SANDBOX_BASE_URL",
        "SHIPROCKET_SANDBOX_SERVICEABILITY_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    provider = ShiprocketProvider()

    assert provider.base_url == "https://api-sandbox.shiprocket.in/v1/external"
    assert provider.serviceability_base_url == "https://serviceability-sandbox.shiprocket.in"


def test_shiprocket_sandbox_honours_explicit_hosts(monkeypatch):
    monkeypatch.setenv("SHIPROCKET_ENV", "sandbox")
    monkeypatch.setenv("SHIPROCKET_SANDBOX_BASE_URL", "https://sandbox.example.test/v1/external")
    monkeypatch.setenv("SHIPROCKET_SANDBOX_SERVICEABILITY_BASE_URL", "https://serviceability.example.test")

    provider = ShiprocketProvider()

    assert provider.base_url == "https://sandbox.example.test/v1/external"
    assert provider.serviceability_base_url == "https://serviceability.example.test"


def test_shiprocket_production_uses_documented_external_api(monkeypatch):
    monkeypatch.setenv("SHIPROCKET_ENV", "production")
    for key in (
        "SHIPROCKET_BASE_URL",
        "SHIPROCKET_SERVICEABILITY_BASE_URL",
        "SHIPROCKET_PRODUCTION_BASE_URL",
        "SHIPROCKET_PRODUCTION_SERVICEABILITY_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    provider = ShiprocketProvider()

    assert provider.base_url == "https://apiv2.shiprocket.in/v1/external"
    assert provider.serviceability_base_url == provider.base_url
