import base64
import hashlib
import hmac
import json
import time

import pytest

from app.core.dependencies import _validate_token_locally
from app.core.exceptions import UnauthenticatedUser


def _segment(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _token(secret: str, payload: dict, algorithm: str = "HS256") -> str:
    header = {"alg": algorithm, "typ": "JWT"}
    encoded_header = _segment(header)
    encoded_payload = _segment(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode()

    if algorithm == "HS256":
        signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    else:
        signature = b"unsupported"

    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def test_validate_token_locally_accepts_valid_hs256():
    token = _token(
        "test-jwt-secret",
        {
            "sub": "user-123",
            "email": "user@example.com",
            "aud": "authenticated",
            "exp": int(time.time()) + 300,
            "user_metadata": {"full_name": "User"},
        },
    )

    user = _validate_token_locally(token)

    assert user is not None
    assert user.id == "user-123"
    assert user.email == "user@example.com"
    assert user.user_metadata["full_name"] == "User"


def test_validate_token_locally_rejects_tampered_signature():
    token = _token(
        "test-jwt-secret",
        {
            "sub": "user-123",
            "aud": "authenticated",
            "exp": int(time.time()) + 300,
        },
    )
    parts = token.split(".")
    parts[1] = _segment(
        {
            "sub": "attacker",
            "aud": "authenticated",
            "exp": int(time.time()) + 300,
        }
    )

    with pytest.raises(UnauthenticatedUser):
        _validate_token_locally(".".join(parts))


def test_validate_token_locally_rejects_expired_token():
    token = _token(
        "test-jwt-secret",
        {
            "sub": "user-123",
            "aud": "authenticated",
            "exp": int(time.time()) - 1,
        },
    )

    with pytest.raises(UnauthenticatedUser):
        _validate_token_locally(token)


def test_validate_token_locally_falls_back_for_non_hs256():
    token = _token(
        "test-jwt-secret",
        {
            "sub": "user-123",
            "aud": "authenticated",
            "exp": int(time.time()) + 300,
        },
        algorithm="RS256",
    )

    assert _validate_token_locally(token) is None
