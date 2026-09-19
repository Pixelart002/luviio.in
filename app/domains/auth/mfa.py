"""Privileged-account MFA via Supabase Auth TOTP."""
from __future__ import annotations

from typing import Any
import logging

import httpx

from app.core.config import settings
from app.domains.auth.http_client import get_auth_http_client


logger = logging.getLogger(__name__)


class MFAError(RuntimeError):
    """Supabase MFA operation failed."""


def _provider_error_message(response: httpx.Response, data: dict[str, Any]) -> str:
    """Return a useful, bounded provider error without exposing tokens/secrets."""
    for key in ("msg", "message", "error_description", "error"):
        value = data.get(key)
        if value:
            return str(value)[:500]
    body = (response.text or "").strip().replace("\n", " ")
    return f"Supabase Auth MFA request failed (HTTP {response.status_code}): {body[:300] or 'empty response'}"


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
        message = _provider_error_message(response, data)
        logger.warning("Supabase MFA provider rejected request: status=%s message=%s", response.status_code, message)
        raise MFAError(message)
    return data if isinstance(data, dict) else {}


async def list_factors(access_token: str) -> dict[str, Any]:
    """List the current user's MFA factors through Supabase's REST exposure.

    Supabase's current MFA documentation exposes the factor list through
    PostgREST at /rest/v1/auth/factors. The Auth /auth/v1/factors route is
    used for factor mutation/challenge operations and returns 405 for GET
    on the current hosted Auth service.
    """
    client = await get_auth_http_client()
    try:
        response = await client.get(
            f"{settings.SB_URL}/rest/v1/auth/factors",
            headers={**_headers(access_token), "Accept": "application/json"},
            params={"select": "id,factor_type,status,friendly_name,created_at"},
        )
    except httpx.RequestError as exc:
        raise MFAError("Authentication service currently unreachable.") from exc

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code >= 400:
        message = _provider_error_message(response, data if isinstance(data, dict) else {})
        logger.warning("Supabase MFA factor-list provider rejected request: status=%s message=%s", response.status_code, message)
        raise MFAError(message)

    factors = data if isinstance(data, list) else []
    return {
        "all": factors,
        "totp": [factor for factor in factors if factor.get("factor_type") == "totp"],
    }


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
