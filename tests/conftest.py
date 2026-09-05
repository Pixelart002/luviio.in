import os
from collections.abc import Iterator

# Set safe test-only defaults before test modules import application packages.
_TEST_ENVIRONMENT = {
    "APP_ENV": "development",
    "SB_URL": "https://test.supabase.co",
    "SB_KEY": "test-anon-key",
    "SB_SERVICE_ROLE_KEY": "test-service-key",
    "SUPABASE_JWT_SECRET": "test-jwt-secret",
    "STRIPE_SECRET_KEY": "sk_test_placeholder",
    "STRIPE_WEBHOOK_SECRET": "whsec_placeholder",
}
os.environ.update(_TEST_ENVIRONMENT)
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "APP_ENV": "development",
        "SB_URL": "https://test.supabase.co",
        "SB_KEY": "test-anon-key",
        "SB_SERVICE_ROLE_KEY": "test-service-key",
        "SUPABASE_JWT_SECRET": "test-jwt-secret",
        "STRIPE_SECRET_KEY": "sk_test_placeholder",
        "STRIPE_WEBHOOK_SECRET": "whsec_placeholder",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    for key in ("RESEND_API_KEY", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def app() -> FastAPI:
    from app.main import app

    return app


@pytest.fixture
def client(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr("app.main.start_cron_jobs", lambda: None)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fake_supabase() -> Mock:
    return Mock()
