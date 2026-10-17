"""Security and regression tests for local Supabase asymmetric JWT verification."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import dependencies


def _signed_token(private_key, *, issuer: str, kid: str = "test-key") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "user-123",
            "email": "customer@example.com",
            "user_metadata": {"full_name": "Customer"},
            "aud": "authenticated",
            "iss": issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )


def test_asymmetric_jwt_is_verified_locally_with_cached_jwks(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://project.supabase.co/auth/v1"
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})

    async def fake_fetch_jwks(*, force_refresh=False):
        return {"keys": [public_jwk]}

    monkeypatch.setattr(dependencies.settings, "SB_URL", "https://project.supabase.co")
    monkeypatch.setattr(dependencies, "_fetch_jwks", fake_fetch_jwks)
    token = _signed_token(private_key, issuer=issuer)

    user = asyncio.run(dependencies._validate_asymmetric_token(token, "RS256"))

    assert user is not None
    assert user.id == "user-123"
    assert user.email == "customer@example.com"
    assert user.user_metadata == {"full_name": "Customer"}


def test_asymmetric_jwt_rejects_wrong_issuer(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})

    async def fake_fetch_jwks(*, force_refresh=False):
        return {"keys": [public_jwk]}

    monkeypatch.setattr(dependencies.settings, "SB_URL", "https://project.supabase.co")
    monkeypatch.setattr(dependencies, "_fetch_jwks", fake_fetch_jwks)
    token = _signed_token(private_key, issuer="https://attacker.example/auth/v1")

    with pytest.raises(dependencies.UnauthenticatedUser):
        asyncio.run(dependencies._validate_asymmetric_token(token, "RS256"))


def test_unsupported_algorithm_keeps_native_verification_fallback():
    token = "header.payload.signature"
    assert asyncio.run(dependencies._validate_asymmetric_token(token, "HS384")) is None
