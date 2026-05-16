"""
Auth Router
============
Changes from original:
  1. send_welcome_email() added after successful registration
  2. Anti-enumeration preserved
  3. Timing attack mitigation on login
  4. FIXED: Safe checks for Supabase Auth responses to prevent NoneType crashes
  5. FIXED: Safe extraction of user_id for logout to prevent KeyErrors
  6. FIXED: Proper AuthApiError handling for refresh tokens
  7. SECURED: Moved Refresh Token to HttpOnly Cookie to prevent XSS attacks.
"""
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status, Depends, Request, Response, Cookie
from gotrue.errors import AuthApiError
from pydantic import BaseModel, EmailStr, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.supabase_client import get_supabase, get_admin_supabase
from app.repositories.user_repo import UserRepository
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])

_MIN_RESPONSE_SECONDS = 0.3


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
    token_type: str
    expires_in: int | None = None
    # refresh_token is intentionally removed from JSON response for XSS protection


class LoginResponse(TokenResponse):
    user: dict[str, str]


class MessageResponse(BaseModel):
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest) -> dict[str, str]:
    """
    Anti-enumeration — always returns same message.
    Flow:
      1. sign_up() with Supabase Auth
      2. Defensively upsert profile row
      3. Send welcome email via Resend (non-fatal)
    """
    sb   = get_supabase()
    adm  = get_admin_supabase()
    repo = UserRepository(adm)

    auth_user_id: str | None = None
    user_name: str = payload.full_name or ""

    try:
        result = sb.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
            "options": {"data": {"full_name": payload.full_name or ""}},
        })
        # SAFE CHECK: Prevent NoneType error if user requires email confirmation
        if result and hasattr(result, "user") and result.user:
            auth_user_id = result.user.id

    except AuthApiError as e:
        logger.info("Register AuthApiError (likely duplicate): %s", e.code)

    except Exception as e:
        logger.error("Registration service error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service unavailable. Please try again later.",
        )

    # ── Defensive profile creation ────────────────────────────────────────────
    if auth_user_id:
        try:
            repo.upsert_profile(
                user_id=auth_user_id,
                email=payload.email,
                full_name=payload.full_name or "",
            )
        except Exception as e:
            logger.warning("Profile upsert after register failed (non-critical): %s", e)

        # ── Welcome email via Resend ──────────────────────────────────────────
        try:
            from app.utils.email import send_welcome_email
            send_welcome_email(payload.email, user_name)
        except Exception as e:
            # Non-fatal — registration still succeeds
            logger.warning("Welcome email failed (non-critical): %s", e)

    return {"message": "If this email is new, a confirmation link has been sent."}


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, response: Response, payload: LoginRequest) -> dict[str, Any]:
    """Constant-time response — timing attack mitigation."""
    start = time.monotonic()
    sb = get_supabase()
    result = None

    try:
        result = sb.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })
        
        # SAFE CHECK: Prevent crash if user or session is missing
        if not result or not hasattr(result, "user") or not result.user or not hasattr(result, "session") or not result.session:
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
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, _MIN_RESPONSE_SECONDS - elapsed))

    # ── Set Refresh Token in HttpOnly Cookie ──────────────────────────────────
    response.set_cookie(
        key="refresh_token",
        value=result.session.refresh_token,
        httponly=True,            # Prevents JS access (XSS mitigation)
        secure=True,              # Change to False if testing locally without HTTPS
        samesite="lax",           # CSRF mitigation
        max_age=7 * 24 * 60 * 60  # 7 days expiry
    )

    return {
        "access_token":  result.session.access_token,
        "token_type":    "bearer",
        "expires_in":    result.session.expires_in,
        "user": {
            "id":    result.user.id,
            "email": result.user.email,
        },
    }


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(None)) -> dict[str, Any]:
    """Uses HttpOnly cookie instead of JSON payload to get the refresh token."""
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing. Please log in again."
        )

    sb = get_supabase()
    try:
        result = sb.auth.refresh_session(refresh_token)
        # SAFE CHECK
        if not result or not hasattr(result, "session") or not result.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
            
    except AuthApiError as e:
        logger.warning(f"AuthApiError during token refresh: {e.message}")
        # Clear invalid cookie
        response.delete_cookie("refresh_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during refresh: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
        
    # Supabase might issue a new refresh token, so update the cookie
    response.set_cookie(
        key="refresh_token",
        value=result.session.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60
    )
        
    return {
        "access_token":  result.session.access_token,
        "token_type":    "bearer",
        "expires_in":    result.session.expires_in,
    }


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    sb = get_admin_supabase()
    try:
        # SAFE CHECK: Extract user ID properly (like we did in payments.py)
        user_id = None
        if "profile" in current and "id" in current["profile"]:
            user_id = current["profile"]["id"]
        elif "id" in current:
            user_id = current["id"]
        elif "sub" in current:
            user_id = current["sub"]

        if user_id:
            sb.auth.admin.sign_out(user_id, scope="global")
        else:
            logger.warning("Logout attempted but no valid user ID found in session.")
            
    except Exception as e:
        logger.warning("Sign out failed (non-critical): %s", e)
        
    # Clear the refresh token cookie
    response.delete_cookie("refresh_token")
        
    return {"message": "Logged out successfully"}


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest) -> dict[str, str]:
    """Anti-enumeration — always same response."""
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
