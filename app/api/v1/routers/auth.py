"""
Auth Router — Async Hardened Production Grade
=============================================
Path: app/api/v1/routers/auth.py
"""
import logging
from typing import Any, Dict
from fastapi import APIRouter, Cookie, Depends, Request, Response, status,HTTPException,Query
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.schemas.auth_dto import (
    RegisterRequest, LoginRequest, ForgotPasswordRequest, 
    ResetPasswordRequest, TokenResponse, LoginResponse, MessageResponse, SessionResponse
)
from app.core.dependencies import get_current_user, get_user_id_strict
from app.services.auth.service import AuthService
from app.permissions.policies.auth_policies import AuthPolicy
from app.constants.auth_messages import AuthMessages, AuthSecurityMessages
from app.utils.timestamp import ts_to_iso

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])

_COOKIE_KWARGS = dict(key="refresh_token", httponly=True, secure=True, samesite="none", path="/api/v1/auth")

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterRequest):
    """Registers a new user identity and provisions database metadata."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating registration for: {payload.email}")

    service = AuthService()
    await service.register_user(payload.email, payload.password, payload.full_name or "", get_remote_address(request))
    
    if hasattr(request.state, "actions"):
        request.state.actions.extend(["Supabase Auth identity established", "Created profile metadata in DB", "Queued async Welcome Email"])
    return {"message": AuthMessages.REGISTER_SUCCESS}

@router.post("/login", status_code=status.HTTP_200_OK, response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, payload: LoginRequest):
    """Authenticates credentials, issues JWT access token and sets HttpOnly refresh cookie."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Authenticating credentials for: {payload.email}")

    service = AuthService()
    session_data = await service.login_user(payload.email, payload.password, get_remote_address(request))

    if hasattr(request.state, "actions"):
        request.state.actions.extend([f"Identity verified -> UID: {session_data['user_id'][:8]}...", "Issued secure HttpOnly Refresh Cookie"])
    
    response.set_cookie(**_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=7 * 24 * 60 * 60)
    return {
        "access_token": session_data["access_token"], 
        "token_type": "bearer",
        "expires_in": session_data["expires_in"], 
        "user": {"id": session_data["user_id"], "email": session_data["email"]},
    }

@router.post("/refresh", status_code=status.HTTP_200_OK, response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(None)):
    """Prolongs active session using valid HttpOnly refresh cookie."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Intercepted session refresh cookie")

    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.INVALID_REFRESH)

    service = AuthService()
    session_data = await service.refresh_user_session(refresh_token)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Session successfully refreshed & prolonged")

    response.set_cookie(**_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=7 * 24 * 60 * 60)
    return {
        "access_token": session_data["access_token"], 
        "token_type": "bearer", 
        "expires_in": session_data["expires_in"]
    }

@router.post("/logout", status_code=status.HTTP_200_OK, response_model=MessageResponse)
async def logout(request: Request, response: Response, refresh_token: str | None = Cookie(None)):
    """Revokes access tokens in vault and clears client HTTP cookies."""
    if hasattr(request.state, "actions"):
        request.state.actions.append("Executing user sign-out sequence")

    await AuthService().logout_user(refresh_token or "")
    response.delete_cookie(**_COOKIE_KWARGS)

    if hasattr(request.state, "actions"):
        request.state.actions.extend(["Revoked active token in Supabase Vault", "Destroyed local HttpOnly auth cookies"])
    return {"message": AuthMessages.LOGOUT_SUCCESS}

@router.post("/forgot-password", status_code=status.HTTP_200_OK, response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    """Dispatches asynchronous recovery email without revealing user existence."""
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Requesting password recovery dispatch for: {payload.email}")
    
    await AuthService().process_forgot_password(payload.email, get_remote_address(request))
    return {"message": AuthMessages.FORGOT_SUCCESS}

@router.post("/reset-password", status_code=status.HTTP_200_OK, response_model=MessageResponse)
async def reset_password(
    request: Request, 
    payload: ResetPasswordRequest, 
    user_id: str = Query(..., description="Target User ID to reset password for"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Overrides account password securely.
    🛡️ Enforces ABAC Policy: Must be the account owner OR a System Admin.
    """
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Validating password override ABAC rules for target: {user_id[:8]}...")

    # Enforce Attribute-Based Access Control (ABAC)
    AuthPolicy.assert_can_reset_password(current_user, user_id)

    await AuthService().process_reset_password(user_id, payload.new_password)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Password updated securely via Admin Vault Hook")
    return {"message": AuthMessages.RESET_SUCCESS}

@router.get("/session", status_code=status.HTTP_200_OK, response_model=SessionResponse)
async def check_session(request: Request, current: Dict[str, Any] = Depends(get_current_user)):
    """Returns metadata of currently active JWT bearer session."""
    user_id = str(current.get("sub") or current.get("profile", {}).get("id", ""))
    email = str(current.get("email") or current.get("profile", {}).get("email", ""))
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Session inspected -> Valid for: {email}")
        
    return {
        "authenticated": True, 
        "user_id": user_id, 
        "email": email, 
        "expires_at": ts_to_iso(current.get("exp"))
    }