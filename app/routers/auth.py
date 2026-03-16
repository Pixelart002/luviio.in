import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status, Depends, Request
from gotrue.errors import AuthApiError
from pydantic import BaseModel, EmailStr, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.supabase_client import get_supabase, get_admin_supabase
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])

_MIN_RESPONSE_SECONDS = 0.3  # Timing attack mitigation


# ── Models ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int | None = None


class LoginResponse(TokenResponse):
    user: dict[str, str]


class MessageResponse(BaseModel):
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest) -> dict[str, str]:
    """
    SECURITY: Email existence kabhi reveal nahi karte (anti-enumeration).
    AuthApiError (duplicate) aur infra errors alag handle hote hain.
    """
    sb = get_supabase()
    try:
        sb.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
            "options": {"data": {"full_name": payload.full_name or ""}},
        })
    except AuthApiError as e:
        logger.info("Register AuthApiError (likely duplicate): %s", e.code)
        # Same response — anti-enumeration
    except Exception as e:
        logger.error("Registration service error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service unavailable. Please try again later.",
        )
    return {"message": "If this email is new, a confirmation link has been sent."}


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest) -> dict[str, Any]:
    """
    SYNC function — Supabase client is synchronous, mixing with async causes event loop block.
    time.sleep for constant-time response (timing attack mitigation).
    """
    start = time.monotonic()
    sb = get_supabase()

    try:
        result = sb.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })
        if not result.user or not result.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
    except HTTPException:
        raise
    except AuthApiError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    except Exception as e:
        logger.error("Login service error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    finally:
        # Constant response time — timing side-channel mitigation
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))

    return {
        "access_token":  result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "token_type":    "bearer",
        "expires_in":    result.session.expires_in,
        "user": {
            "id":    result.user.id,
            "email": result.user.email,
        },
    }


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
def refresh(request: Request, payload: RefreshRequest) -> dict[str, Any]:
    """
    NOTE: Enable Refresh Token Rotation in Supabase Dashboard:
    Auth → JWT Settings → Enable Token Rotation + Reuse Interval: 0
    """
    sb = get_supabase()
    try:
        result = sb.auth.refresh_session(payload.refresh_token)
        if not result.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    return {
        "access_token":  result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "token_type":    "bearer",
        "expires_in":    result.session.expires_in,
    }


@router.post("/logout", response_model=MessageResponse)
def logout(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """
    NOTE: Set JWT expiry to 15 min for true invalidation:
    Dashboard → Auth → JWT Settings → JWT expiry
    """
    sb = get_admin_supabase()
    try:
        user_id: str = current["profile"]["id"]
        sb.auth.admin.sign_out(user_id, scope="global")
    except Exception as e:
        logger.warning("Sign out failed (non-critical): %s", e)
    return {"message": "Logged out successfully"}


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest) -> dict[str, str]:
    """
    SECURITY: Always same response — don't reveal if email exists.
    """
    sb = get_supabase()
    try:
        sb.auth.reset_password_email(payload.email)
    except Exception as e:
        logger.warning("Password reset email failed: %s", e)
    return {"message": "If this email exists, a password reset link has been sent."}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    payload: ResetPasswordRequest,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """
    User reset link pe click karta hai — Supabase token se authenticated hota hai.
    Us token se /login kar, phir ye endpoint hit karo.
    """
    sb = get_supabase()
    try:
        sb.auth.update_user({"password": payload.new_password})
    except AuthApiError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password reset failed: {e.message}",
        )
    except Exception as e:
        logger.error("Password reset error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable",
        )
    return {"message": "Password updated successfully"}