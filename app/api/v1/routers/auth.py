"""
Auth Router — Enterprise Grade
===============================
Path: app/api/v1/routers/auth.py

Architecture Upgrades:
  1. Supabase SDK imports completely removed!
  2. All external Auth API logic delegated to AuthRepository.
  3. Clean architecture strictly enforced.
"""
import logging
import time
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from gotrue.errors import AuthApiError
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS
from app.api.schemas.auth_dto import (
    RegisterRequest, LoginRequest, ForgotPasswordRequest, 
    ResetPasswordRequest, TokenResponse, LoginResponse, MessageResponse
)
from app.core.dependencies import get_current_user
from app.repositories.user_repo import UserRepository
from app.repositories.auth_repo import AuthRepository
from app.integrations.email.registry import get_email_provider

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Constants & Config ────────────────────────────────────────────────────────
_MIN_RESPONSE_SECONDS = 0.3
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_COOLDOWN_SECONDS = 900

_COOKIE_KWARGS = dict(
    key="refresh_token", httponly=True, secure=True,
    samesite="none", path="/api/v1/auth",
)

# ── Brute Force Protection (In-Memory) ────────────────────────────────────────
_login_attempts: dict[str, list[float]] = {}
_blocked_ips: dict[str, float] = {}

def _check_brute_force(ip: str, email: str = "") -> bool:
    now = time.time()
    global _login_attempts, _blocked_ips
    
    _login_attempts = {k: [t for t in v if now - t < _LOGIN_WINDOW_SECONDS] for k, v in _login_attempts.items()}
    _login_attempts = {k: v for k, v in _login_attempts.items() if v}
    _blocked_ips = {k: v for k, v in _blocked_ips.items() if v > now}
    
    if ip in _blocked_ips: return True
    
    email_key = f"email:{email}" if email else None
    if email_key and email_key in _blocked_ips: return True
    
    ip_attempts = len(_login_attempts.get(ip, []))
    email_attempts = len(_login_attempts.get(email_key, [])) if email_key else 0
    
    return ip_attempts >= _MAX_LOGIN_ATTEMPTS or email_attempts >= _MAX_LOGIN_ATTEMPTS

def _record_attempt(ip: str, email: str = "") -> None:
    now = time.time()
    _login_attempts.setdefault(ip, []).append(now)
    if email: _login_attempts.setdefault(f"email:{email}", []).append(now)
    
    if len(_login_attempts[ip]) >= _MAX_LOGIN_ATTEMPTS:
        _blocked_ips[ip] = now + _LOGIN_COOLDOWN_SECONDS
        logger.warning("IP BLOCKED | ip=%s attempts=%d", ip, len(_login_attempts[ip]))
    
    if email:
        email_key = f"email:{email}"
        if len(_login_attempts.get(email_key, [])) >= _MAX_LOGIN_ATTEMPTS:
            _blocked_ips[email_key] = now + _LOGIN_COOLDOWN_SECONDS

def _reset_attempts(ip: str, email: str = "") -> None:
    _login_attempts.pop(ip, None)
    _blocked_ips.pop(ip, None)
    if email:
        _login_attempts.pop(f"email:{email}", None)
        _blocked_ips.pop(f"email:{email}", None)

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest) -> dict[str, str]:
    client_ip = get_remote_address(request)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Registration initiated for: {payload.email}")
    
    if _check_brute_force(client_ip):
        raise HTTPException(429, "Too many attempts. Please try again later.")
    
    auth_repo = AuthRepository()
    user_repo = UserRepository()

    auth_user_id: str | None = None
    user_name: str = payload.full_name or ""

    try:
        auth_user_id = auth_repo.sign_up(payload.email, payload.password, user_name)
        if auth_user_id and hasattr(request.state, "actions"): 
            request.state.actions.append("User successfully created via AuthRepository")
    except AuthApiError:
        _record_attempt(client_ip)
    except Exception:
        raise HTTPException(503, "Registration service unavailable. Please try again later.")

    if auth_user_id:
        try:
            user_repo.upsert_profile(user_id=auth_user_id, email=payload.email, full_name=user_name)
            if hasattr(request.state, "actions"): request.state.actions.append("User profile saved to database")
        except Exception as e:
            logger.warning("Profile upsert after register failed: %s", e)

        try:
            email_service = get_email_provider("resend")
            email_service.send_welcome_email(payload.email, user_name)
            if hasattr(request.state, "actions"): request.state.actions.append("Welcome email dispatched")
        except Exception as e:
            logger.warning("Welcome email failed: %s", e)

    return {"message": "If this email is new, a confirmation link has been sent."}


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, response: Response, payload: LoginRequest) -> dict[str, Any]:
    start = time.monotonic()
    client_ip = get_remote_address(request)
    auth_repo = AuthRepository()
    
    if hasattr(request.state, "actions"): request.state.actions.append(f"Login attempt via email: {payload.email}")
    
    if _check_brute_force(client_ip, payload.email):
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))
        raise HTTPException(429, "Too many login attempts. Please try again in 15 minutes.")

    try:
        session_data = auth_repo.sign_in(payload.email, payload.password)
        if not session_data:
            _record_attempt(client_ip, payload.email)
            raise HTTPException(401, "Invalid email or password")
    except (HTTPException, AuthApiError):
        _record_attempt(client_ip, payload.email)
        raise HTTPException(401, "Invalid email or password")
    except Exception:
        raise HTTPException(503, "Authentication service unavailable")
    finally:
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))

    _reset_attempts(client_ip, payload.email)
    response.set_cookie(**_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=7 * 24 * 60 * 60)

    if hasattr(request.state, "actions"):
        request.state.actions.extend(["Auth validated credentials", "Refresh token securely stored in HttpOnly cookie"])
    if hasattr(request.state, "user_name"):
        request.state.user_id = session_data["user_id"]
        request.state.user_name = session_data["email"]

    return {
        "access_token": session_data["access_token"], "token_type": "bearer",
        "expires_in": session_data["expires_in"], "user": {"id": session_data["user_id"], "email": session_data["email"]},
    }

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(None)) -> dict[str, Any]:
    if not refresh_token: raise HTTPException(401, "Refresh token missing. Please log in again.")
    auth_repo = AuthRepository()
    
    try:
        session_data = auth_repo.refresh_session(refresh_token)
        if not session_data:
            response.delete_cookie(**_COOKIE_KWARGS)
            raise HTTPException(401, "Invalid refresh token")
    except Exception:
        response.delete_cookie(**_COOKIE_KWARGS)
        raise HTTPException(401, "Invalid or expired refresh token")

    response.set_cookie(**_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=7 * 24 * 60 * 60)
    
    if hasattr(request.state, "user_name") and session_data["user_id"]:
        request.state.user_id = session_data["user_id"]
        request.state.user_name = session_data["email"]

    return {"access_token": session_data["access_token"], "token_type": "bearer", "expires_in": session_data["expires_in"]}

@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, refresh_token: str | None = Cookie(None)) -> dict[str, str]:
    if refresh_token:
        try:
            auth_repo = AuthRepository()
            session_data = auth_repo.refresh_session(refresh_token)
            if session_data: auth_repo.sign_out()
        except Exception: pass

    response.delete_cookie(**_COOKIE_KWARGS)
    return {"message": "Logged out successfully"}

@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest) -> dict[str, str]:
    client_ip = get_remote_address(request)
    if _check_brute_force(client_ip): raise HTTPException(429, "Too many attempts. Please try again later.")
    
    try:
        AuthRepository().reset_password_email(payload.email)
    except Exception: pass

    return {"message": "If this email exists, a password reset link has been sent."}

@router.post("/reset-password", response_model=MessageResponse)
def reset_password(request: Request, payload: ResetPasswordRequest, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    user_id = current.get("sub") or current.get("id") or current.get("profile", {}).get("id")
    if not user_id: raise HTTPException(401, "Valid user session not found")

    try:
        AuthRepository().admin_update_password(user_id, payload.new_password)
    except AuthApiError as e: raise HTTPException(400, f"Password reset failed: {e.message}")
    except Exception: raise HTTPException(503, "Service unavailable")

    return {"message": "Password updated successfully"}

@router.get("/session", response_model=dict)
def check_session(request: Request, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = current.get("sub") or current.get("profile", {}).get("id", "")
    email = current.get("email") or current.get("profile", {}).get("email", "")
    return {"authenticated": True, "user_id": user_id, "email": email, "expires_at": current.get("exp")}