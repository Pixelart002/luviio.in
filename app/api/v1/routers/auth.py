import logging
from typing import Any

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.schemas.auth_dto import (
    RegisterRequest, LoginRequest, ForgotPasswordRequest, 
    ResetPasswordRequest, TokenResponse, LoginResponse, MessageResponse
)
from app.core.dependencies import get_current_user, get_user_id_strict
from app.services.auth.service import AuthService

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])

_COOKIE_KWARGS = dict(key="refresh_token", httponly=True, secure=True, samesite="none", path="/api/v1/auth")

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterRequest):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating registration for: {payload.email}")

    service = AuthService()
    await service.register_user(payload.email, payload.password, payload.full_name or "", get_remote_address(request))
    
    if hasattr(request.state, "actions"):
        request.state.actions.extend(["Supabase Auth identity established", "Created profile metadata in DB", "Queued async Welcome Email"])
    return {"message": "If this email is new, a confirmation link has been sent."}

@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, payload: LoginRequest):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Authenticating credentials for: {payload.email}")

    service = AuthService()
    session_data = await service.login_user(payload.email, payload.password, get_remote_address(request))

    if hasattr(request.state, "actions"):
        request.state.actions.extend([f"Identity verified -> UID: {session_data['user_id'][:8]}...", "Issued secure HttpOnly Refresh Cookie"])
    
    response.set_cookie(**_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=7 * 24 * 60 * 60)
    return {
        "access_token": session_data["access_token"], "token_type": "bearer",
        "expires_in": session_data["expires_in"], "user": {"id": session_data["user_id"], "email": session_data["email"]},
    }

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(None)):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Intercepted session refresh cookie")

    service = AuthService()
    session_data = await service.refresh_user_session(refresh_token)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Session successfully refreshed & prolonged")

    response.set_cookie(**_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=7 * 24 * 60 * 60)
    return {"access_token": session_data["access_token"], "token_type": "bearer", "expires_in": session_data["expires_in"]}

@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response, refresh_token: str | None = Cookie(None)):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Executing user sign-out sequence")

    await AuthService().logout_user(refresh_token)
    response.delete_cookie(**_COOKIE_KWARGS)

    if hasattr(request.state, "actions"):
        request.state.actions.extend(["Revoked active token in Supabase Vault", "Destroyed local HttpOnly auth cookies"])
    return {"message": "Logged out successfully"}

@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Requesting password recovery dispatch for: {payload.email}")
    
    await AuthService().process_forgot_password(payload.email, get_remote_address(request))
    return {"message": "If this email exists, a password reset link has been sent."}

@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(request: Request, payload: ResetPasswordRequest, user_id: str = Depends(get_user_id_strict)):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Validating password override for user: {user_id[:8]}...")

    await AuthService().process_reset_password(user_id, payload.new_password)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Password updated securely via Admin Hook")
    return {"message": "Password updated successfully"}

@router.get("/session", response_model=dict)
async def check_session(request: Request, current: dict[str, Any] = Depends(get_current_user)):
    user_id = current.get("sub") or current.get("profile", {}).get("id", "")
    email = current.get("email") or current.get("profile", {}).get("email", "")
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Session inspected -> Valid for: {email}")
    return {"authenticated": True, "user_id": user_id, "email": email, "expires_at": current.get("exp")}