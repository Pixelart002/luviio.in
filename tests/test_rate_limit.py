from types import SimpleNamespace

from app.core import rate_limit


class FakeRequest:
    def __init__(self, host="10.0.0.10", headers=None):
        self.client = SimpleNamespace(host=host)
        self.headers = headers or {}


def test_untrusted_peer_cannot_spoof_forwarded_client_ip(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "trusted_proxy_ips", [])
    request = FakeRequest(
        host="10.0.0.10",
        headers={
            "CF-Connecting-IP": "203.0.113.50",
            "X-Forwarded-For": "203.0.113.51",
            "X-Real-IP": "203.0.113.52",
        },
    )

    assert rate_limit._get_client_ip(request) == "10.0.0.10"


def test_trusted_proxy_uses_valid_cloudflare_client_ip(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "trusted_proxy_ips", ["10.0.0.10"])
    request = FakeRequest(
        host="10.0.0.10",
        headers={"CF-Connecting-IP": "203.0.113.50"},
    )

    assert rate_limit._get_client_ip(request) == "203.0.113.50"


def test_trusted_proxy_rejects_invalid_forwarded_ip(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "trusted_proxy_ips", ["10.0.0.10"])
    request = FakeRequest(
        host="10.0.0.10",
        headers={"X-Forwarded-For": "not-an-ip"},
    )

    assert rate_limit._get_client_ip(request) == "10.0.0.10"


def test_trusted_proxy_supports_cidr(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "trusted_proxy_ips", ["10.0.0.0/24"])
    request = FakeRequest(
        host="10.0.0.25",
        headers={"X-Real-IP": "203.0.113.60"},
    )

    assert rate_limit._get_client_ip(request) == "203.0.113.60"
