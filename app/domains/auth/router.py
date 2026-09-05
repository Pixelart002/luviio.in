"""
Auth Router — Async Standardized Endpoints
==========================================
Path: app/domains/auth/router.py
"""
import logging
from typing import Any
from fastapi import APIRouter, Cookie, Depends, Request, Response, status, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.domains.auth.schemas import RegisterRequest, LoginRequest, ForgotPasswordRequest, ResetPasswordRequest
from app.core.dependencies import get_current_user
from app.domains.auth.service import AuthService
from app.constants.auth_messages import AuthMessages, AuthSecurityMessages
from app.utils.response import success_response

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])
_COOKIE_KWARGS = dict(key="refresh_token", httponly=True, secure=True, samesite="none", path="/api/v1/auth")

@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterRequest):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating registration for: {payload.email}")
    client_ip = get_remote_address(request) or "0.0.0.0"
    await AuthService().register_user(payload.email, payload.password, payload.full_name or "", client_ip)
    if hasattr(request.state, "actions"):
        request.state.actions.extend(["Supabase Auth identity established", "Created profile metadata in DB", "Queued async Welcome Email"])
    return success_response(message=AuthMessages.REGISTER_SUCCESS)

@router.post("/login", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, payload: LoginRequest):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Authenticating credentials for: {payload.email}")
    client_ip = get_remote_address(request) or "0.0.0.0"
    session_data = await AuthService().login_user(payload.email, payload.password, client_ip)
    if hasattr(request.state, "actions"):
        request.state.actions.extend([f"Identity verified -> UID: {session_data['user_id'][:8]}...", "Issued secure HttpOnly Refresh Cookie"])
    response.set_cookie(**_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=7 * 24 * 60 * 60)
    data = {"access_token": session_data["access_token"], "token_type": "bearer", "expires_in": session_data["expires_in"], "user": {"id": session_data["user_id"], "email": session_data["email"]}}
    return success_response(data=data)

@router.post("/refresh", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(None)):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Intercepted session refresh cookie")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.INVALID_REFRESH_TOKEN)
    session_data = await AuthService().refresh_user_session(refresh_token)
    if hasattr(request.state, "actions"):
        request.state.actions.append("Session successfully refreshed & prolonged")
    response.set_cookie(**_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=7 * 24 * 60 * 60)
    return success_response(data={"access_token": session_data["access_token"], "token_type": "bearer", "expires_in": session_data["expires_in"]})

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, refresh_token: str | None = Cookie(None)):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Executing user sign-out sequence")
    await AuthService().logout_user(refresh_token)
    response.delete_cookie(**_COOKIE_KWARGS)
    if hasattr(request.state, "actions"):
        request.state.actions.extend(["Revoked active token in Supabase Vault", "Destroyed local HttpOnly auth cookies"])
    return success_response(message=AuthMessages.LOGOUT_SUCCESS)

@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Requesting password recovery dispatch for: {payload.email}")
    client_ip = get_remote_address(request) or "0.0.0.0"
    await AuthService().process_forgot_password(payload.email, client_ip)
    return success_response(message=AuthMessages.FORGOT_PWD_SUCCESS)

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(request: Request, payload: ResetPasswordRequest):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Validating secure recovery token for password reset...")
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.MISSING_AUTH_HEADER)
    access_token = auth_header.split(" ")[1]
    await AuthService().process_reset_password(access_token, payload.new_password)
    if hasattr(request.state, "actions"):
        request.state.actions.append("Password updated securely via User Context (IDOR Prevented)")
    return success_response(message=AuthMessages.RESET_PWD_SUCCESS)

@router.get("/session", status_code=status.HTTP_200_OK)
async def check_session(request: Request, current: dict[str, Any] = Depends(get_current_user)):
    user_id = current.get("sub") or current.get("profile", {}).get("id", "")
    email = current.get("email") or current.get("profile", {}).get("email", "")
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Session inspected -> Valid for: {email}")
    return success_response(data={"authenticated": True, "user_id": user_id, "email": email, "expires_at": current.get("exp")}, message=AuthMessages.SESSION_VALID)
