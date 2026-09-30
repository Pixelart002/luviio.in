from app.integrations.shipping.shiprocket import ShiprocketProvider


def test_shiprocket_sandbox_alias_uses_documented_external_api(monkeypatch):
    monkeypatch.setenv("SHIPROCKET_ENV", "sandbox")
    for key in (
        "SHIPROCKET_BASE_URL",
        "SHIPROCKET_SERVICEABILITY_BASE_URL",
        "SHIPROCKET_TEST_EMAIL",
        "SHIPROCKET_TEST_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)

    provider = ShiprocketProvider()

    assert provider.environment == "test"
    assert provider.base_url == "https://apiv2.shiprocket.in/v1/external"
    assert provider.serviceability_base_url == provider.base_url


def test_shiprocket_test_credentials_fall_back_to_generic_credentials(monkeypatch):
    monkeypatch.setenv("SHIPROCKET_ENV", "test")
    monkeypatch.delenv("SHIPROCKET_TEST_EMAIL", raising=False)
    monkeypatch.delenv("SHIPROCKET_TEST_PASSWORD", raising=False)
    monkeypatch.setenv("SHIPROCKET_EMAIL", "test@example.invalid")
    monkeypatch.setenv("SHIPROCKET_PASSWORD", "test-password")

    provider = ShiprocketProvider()

    assert provider.environment == "test"
    assert provider.email == "test@example.invalid"
    assert provider.password == "test-password"
    assert provider.base_url == "https://apiv2.shiprocket.in/v1/external"


def test_shiprocket_explicit_base_url_is_honoured(monkeypatch):
    monkeypatch.setenv("SHIPROCKET_ENV", "test")
    monkeypatch.setenv("SHIPROCKET_BASE_URL", "https://provider.example.test/v1/external")

    provider = ShiprocketProvider()

    assert provider.base_url == "https://provider.example.test/v1/external"
    assert provider.serviceability_base_url == provider.base_url


def test_shiprocket_production_uses_documented_external_api(monkeypatch):
    monkeypatch.setenv("SHIPROCKET_ENV", "production")
    for key in (
        "SHIPROCKET_BASE_URL",
        "SHIPROCKET_SERVICEABILITY_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    provider = ShiprocketProvider()

    assert provider.base_url == "https://apiv2.shiprocket.in/v1/external"
    assert provider.serviceability_base_url == provider.base_url
