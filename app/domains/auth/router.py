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
        request.state.actions.append("Registration request received")
    data = await AuthService().register(payload)
    return success_response(data=data, message=AuthMessages.REGISTERED)

@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest, response: Response):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Login request received")
    data = await AuthService().login(payload)
    refresh_token = data.pop("refresh_token", None)
    if refresh_token:
        response.set_cookie(value=refresh_token, **_COOKIE_KWARGS)
    return success_response(data=data, message=AuthMessages.LOGIN_SUCCESS)

@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    await AuthService().forgot_password(payload.email)
    return success_response(message=AuthMessages.PASSWORD_RESET_SENT)

@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, payload: ResetPasswordRequest):
    await AuthService().reset_password(payload.token, payload.password)
    return success_response(message=AuthMessages.PASSWORD_RESET_SUCCESS)

@router.post("/refresh")
@limiter.limit("20/minute")
async def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(default=None)):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.MISSING_REFRESH_TOKEN)
    data = await AuthService().refresh(refresh_token)
    new_refresh = data.pop("refresh_token", None)
    if new_refresh:
        response.set_cookie(value=new_refresh, **_COOKIE_KWARGS)
    return success_response(data=data, message=AuthMessages.TOKEN_REFRESHED)

@router.post("/logout")
async def logout(request: Request, response: Response, current_user: dict[str, Any] = Depends(get_current_user)):
    await AuthService().logout(current_user)
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    return success_response(message=AuthMessages.LOGOUT_SUCCESS)
