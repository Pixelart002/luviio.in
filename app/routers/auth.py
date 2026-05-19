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
  8. CROSS-ORIGIN FIX: Updated cookies to samesite="none" and secure=True for cross-domain auth.
  9. FIXED: logout ab expired/malformed JWT pe bhi kaam karta hai — get_current_user
     dependency hata di, refresh_token cookie se session invalidate hota hai.
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

# Cookie helper — ek jagah define, sab jagah reuse
_COOKIE_KWARGS = dict(
    key="refresh_token",
    httponly=True,
    secure=True,
    samesite="none",
)


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
    # refresh_token intentionally removed from JSON — XSS protection


class LoginResponse(TokenResponse):
    user: dict[str, str]


class MessageResponse(BaseModel):
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest) -> dict[str, str]:
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

    if auth_user_id:
        try:
            repo.upsert_profile(
                user_id=auth_user_id,
                email=payload.email,
                full_name=payload.full_name or "",
            )
        except Exception as e:
            logger.warning("Profile upsert after register failed (non-critical): %s", e)

        try:
            from app.utils.email import send_welcome_email
            send_welcome_email(payload.email, user_name)
        except Exception as e:
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

        if (
            not result
            or not hasattr(result, "user") or not result.user
            or not hasattr(result, "session") or not result.session
        ):
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

    response.set_cookie(
        **_COOKIE_KWARGS,
        value=result.session.refresh_token,
        max_age=7 * 24 * 60 * 60,
    )

    return {
        "access_token": result.session.access_token,
        "token_type":   "bearer",
        "expires_in":   result.session.expires_in,
        "user": {
            "id":    result.user.id,
            "email": result.user.email,
        },
    }


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(None),
) -> dict[str, Any]:
    """HttpOnly cookie se refresh token leta hai."""

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing. Please log in again.",
        )

    sb = get_supabase()
    try:
        result = sb.auth.refresh_session(refresh_token)
        if not result or not hasattr(result, "session") or not result.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

    except AuthApiError as e:
        logger.warning("AuthApiError during token refresh: %s", e.message)
        response.delete_cookie(**_COOKIE_KWARGS)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error during refresh: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    response.set_cookie(
        **_COOKIE_KWARGS,
        value=result.session.refresh_token,
        max_age=7 * 24 * 60 * 60,
    )

    return {
        "access_token": result.session.access_token,
        "token_type":   "bearer",
        "expires_in":   result.session.expires_in,
    }


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(None),  # FIX: JWT dependency hatayi
) -> dict[str, str]:
    """
    FIX: get_current_user dependency hata di.
    Expired ya malformed access token hone par bhi logout kaam karta hai.
    
    Strategy:
      1. Refresh token cookie se Supabase session invalidate karo
      2. Cookie hamesha clear karo — chahe session invalidation fail bhi ho
      3. Hamesha 200 return karo (user ka perspective: logout = done)
    """
    # ── Step 1: Supabase session invalidate karo ─────────────────────────────
    if refresh_token:
        try:
            sb = get_supabase()
            # Pehle refresh karke valid session lo, phir sign out karo
            result = sb.auth.refresh_session(refresh_token)
            if result and hasattr(result, "session") and result.session:
                sb.auth.sign_out()
        except Exception as e:
            # Non-critical — cookie toh clear hogi hi
            logger.warning("Session invalidation during logout failed (non-critical): %s", e)
    else:
        logger.info("Logout called with no refresh token cookie — clearing anyway.")

    # ── Step 2: Cookie hamesha clear karo ────────────────────────────────────
    response.delete_cookie(**_COOKIE_KWARGS)

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
