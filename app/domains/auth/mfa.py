"""Privileged-account MFA via Supabase Auth TOTP."""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.domains.auth.http_client import get_auth_http_client


class MFAError(RuntimeError):
    """Supabase MFA operation failed."""


def _headers(access_token: str) -> dict[str, str]:
    return {
        "apikey": settings.SB_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


async def _request(
    method: str,
    path: str,
    access_token: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    client = await get_auth_http_client()
    try:
        response = await client.request(
            method,
            f"{settings.SB_URL}{path}",
            headers=_headers(access_token),
            json=json_body,
        )
    except httpx.RequestError as exc:
        raise MFAError("Authentication service currently unreachable.") from exc

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code >= 400:
        message = data.get("msg") or data.get("message") or data.get("error_description")
        raise MFAError(str(message or "MFA operation rejected."))
    return data if isinstance(data, dict) else {}


async def list_factors(access_token: str) -> dict[str, Any]:
    return await _request("GET", "/auth/v1/factors", access_token)


async def enroll_totp(access_token: str, friendly_name: str = "Luviio Admin") -> dict[str, Any]:
    return await _request(
        "POST",
        "/auth/v1/factors",
        access_token,
        json_body={"factor_type": "totp", "friendly_name": friendly_name},
    )


async def challenge(access_token: str, factor_id: str) -> dict[str, Any]:
    return await _request(
        "POST",
        f"/auth/v1/factors/{factor_id}/challenge",
        access_token,
        json_body={},
    )


async def verify(
    access_token: str,
    factor_id: str,
    challenge_id: str,
    code: str,
) -> dict[str, Any]:
    return await _request(
        "POST",
        f"/auth/v1/factors/{factor_id}/verify",
        access_token,
        json_body={"challenge_id": challenge_id, "code": code},
    )


async def unenroll(access_token: str, factor_id: str) -> dict[str, Any]:
    return await _request(
        "DELETE",
        f"/auth/v1/factors/{factor_id}",
        access_token,
    )
