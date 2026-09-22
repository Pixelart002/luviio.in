"""
Dependencies — Async Hardened Production Grade (Luviio SSOT)
============================================================
Path: app/core/dependencies.py
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional

from cachetools import TTLCache
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gotrue.errors import AuthApiError

from app.core.config import settings
from app.core.exceptions import MFARequired, UnauthenticatedUser, UnauthorizedAction
from app.core.supabase import get_async_admin_supabase
from app.domains.users.repository import AsyncUserRepository
from app.enums.roles import UserRole
from app.permissions.base import get_static_role_permissions
from app.permissions.overrides import get_effective_permissions
from app.utils.timestamp import ts_to_iso

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)
_token_cache: TTLCache = TTLCache(maxsize=1024, ttl=60)
_profile_cache: TTLCache = TTLCache(maxsize=1024, ttl=60)


def invalidate_profile_cache(user_id: str) -> None:
    """Invalidate cached profile/RBAC context after an administrative mutation."""
    if user_id:
        _profile_cache.pop(str(user_id), None)


def _extract_token(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    if credentials and credentials.credentials:
        return credentials.credentials
    token = request.cookies.get("access_token")
    if token:
        return token
    raise UnauthenticatedUser("Authentication credentials missing.")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _extract_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        return json.loads(_b64url_decode(parts[1]))
    except Exception:
        return {}


def _validate_token_locally(token: str) -> Optional[Any]:
    """
    Validate legacy Supabase HS256 access tokens without a network round-trip.

    Returns None for tokens that cannot be locally verified (for example RS256),
    so the existing native Supabase Auth validation remains the compatibility
    fallback for asymmetric/project configurations.
    """
    secret = settings.SUPABASE_JWT_SECRET
    if not secret:
        return None

    parts = token.split(".")
    if len(parts) != 3:
        raise UnauthenticatedUser("Token is invalid or expired.")

    try:
        header = json.loads(_b64url_decode(parts[0]))
        if header.get("alg") != "HS256":
            return None

        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        supplied_signature = _b64url_decode(parts[2])
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()

        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise UnauthenticatedUser("Token is invalid or expired.")

        claims = json.loads(_b64url_decode(parts[1]))
        subject = str(claims.get("sub") or "")
        if not subject:
            raise UnauthenticatedUser("Token subject is missing.")

        expires_at = claims.get("exp")
        if expires_at is None or float(expires_at) <= time.time():
            raise UnauthenticatedUser("Token is invalid or expired.")

        not_before = claims.get("nbf")
        if not_before is not None and float(not_before) > time.time():
            raise UnauthenticatedUser("Token is not active yet.")

        audience = claims.get("aud")
        if audience not in (None, "authenticated", ["authenticated"]):
            raise UnauthenticatedUser("Token audience is invalid.")

        return SimpleNamespace(
            id=subject,
            email=str(claims.get("email") or ""),
            user_metadata=claims.get("user_metadata") or {},
        )
    except UnauthenticatedUser:
        raise
    except (TypeError, ValueError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        logger.debug("Local JWT validation failed structurally: %s", exc)
        raise UnauthenticatedUser("Token is invalid or expired.") from exc


async def _validate_token_natively(token: str) -> Any:
    if token in _token_cache:
        return _token_cache[token]

    local_user = _validate_token_locally(token)
    if local_user is not None:
        _token_cache[token] = local_user
        return local_user

    sb = await get_async_admin_supabase()
    try:
        result = await sb.auth.get_user(token)
        user = getattr(result, "user", result)
        if not user or not hasattr(user, "id"):
            raise UnauthenticatedUser("Invalid token structure")
        _token_cache[token] = user
        return user
    except AuthApiError as e:
        logger.warning("Native Auth Block: %s", e)
        raise UnauthenticatedUser("Token is invalid or expired.")
    except Exception as e:
        logger.error("Token validation error: %s", e)
        raise UnauthenticatedUser("Authentication failed.")


async def _get_or_create_profile(user_id: str, email: str, user_metadata: dict) -> Dict[str, Any]:
    if user_id in _profile_cache:
        return _profile_cache[user_id]
    repo = AsyncUserRepository()
    profile = await repo.get_profile(user_id)
    if not profile:
        try:
            profile = await repo.upsert_profile(
                user_id=user_id, email=email,
                full_name=user_metadata.get("full_name", ""), phone=""
            )
        except Exception as e:
            logger.error("Profile auto-create failed for %s: %s", user_id, e)
            return {}
    if profile:
        _profile_cache[user_id] = profile
    return profile or {}


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict[str, Any]:
    token = _extract_token(request, credentials)
    auth_user = await _validate_token_natively(token)
    user_id = str(getattr(auth_user, "id", ""))
    email = getattr(auth_user, "email", "")
    user_metadata = getattr(auth_user, "user_metadata", {}) or {}
    payload = _extract_jwt_payload(token)
    profile = await _get_or_create_profile(user_id, email, user_metadata)
    if profile and not profile.get("is_active", True):
        raise UnauthorizedAction("Account has been deactivated.")
    request.state.user_id = user_id
    request.state.access_token = token
    request.state.user_name = profile.get("full_name") or email.split("@")[0] if email else "User"
    return {
        "sub": user_id,
        "email": email,
        "profile": profile,
        "jwt_role": profile.get("role", "customer"),
        "exp": ts_to_iso(payload.get("exp")),
        "aal": str(payload.get("aal") or "aal1"),
        "access_token": token,
        "auth_user": auth_user
    }


async def get_user_id_strict(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    user_id = current_user.get("sub")
    if not user_id:
        raise UnauthenticatedUser("User identity missing for scope resolution.")
    return str(user_id)


def get_order_payment_port():
    """Composition-root dependency that supplies the Orders payment port."""
    from app.integrations.payments.order_adapter import PaymentsOrderAdapter
    return PaymentsOrderAdapter()


def require_permission(required_perm: str) -> Callable:
    async def permission_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        role = current_user.get("profile", {}).get(
            "role",
            UserRole.CUSTOMER.value if hasattr(UserRole.CUSTOMER, "value") else "customer",
        )
        static_base = get_static_role_permissions(role)
        user_perms = await get_effective_permissions(role, static_base)
        if role != UserRole.CUSTOMER.value and current_user.get("aal", "aal1") != "aal2":
            logger.warning(
                "MFA Block | Privileged user %s attempted %s at %s",
                current_user.get("sub"),
                required_perm,
                current_user.get("aal", "aal1"),
            )
            raise MFARequired()
        if "*" in user_perms:
            return current_user
        if required_perm not in user_perms:
            logger.warning("PBAC Block | User %s missing perm: %s", current_user.get("sub"), required_perm)
            raise UnauthorizedAction(f"Missing required permission: {required_perm}")
        return current_user
    return permission_checker
