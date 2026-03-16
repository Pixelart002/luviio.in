import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.supabase_client import get_supabase, get_admin_supabase
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Request / Response models ─────────────────────────────────────────────────

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


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int | None = None


class UserInfo(BaseModel):
    id: str
    email: str


class LoginResponse(TokenResponse):
    user: UserInfo


class MessageResponse(BaseModel):
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest) -> dict[str, str]:
    """
    Register karo. 
    SECURITY: Email existence kabhi reveal nahi karte (anti-enumeration).
    """
    sb = get_supabase()
    try:
        result = sb.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
            "options": {"data": {"full_name": payload.full_name or ""}},
        })
        if not result.user:
            # Log but don't expose reason
            logger.warning("Registration returned no user for email hash: %s", hash(payload.email))
    except Exception as e:
        msg = str(e).lower()
        # Log for ops visibility, but return same response always
        logger.info("Registration attempt result: %s", msg)

    # ALWAYS same response — attacker ko pata nahi chalega email exist karti hai ya nahi
    return {"message": "If this email is new, a confirmation link has been sent."}


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest) -> dict[str, Any]:
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
    except Exception as e:
        # Distinguish auth failure from infra failure
        msg = str(e).lower()
        if any(k in msg for k in ("invalid", "wrong", "not found", "credentials")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        logger.error("Login service error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    return {
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "token_type": "bearer",
        "expires_in": result.session.expires_in,
        "user": {
            "id": result.user.id,
            "email": result.user.email,
        },
    }


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
def refresh(request: Request, payload: RefreshRequest) -> dict[str, Any]:
    """
    NOTE: Supabase Dashboard mein "Refresh Token Rotation" enable karo.
    Ye automatically purana refresh_token invalidate karta hai.
    Dashboard → Auth → JWT Settings → Enable Token Rotation
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
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "token_type": "bearer",
        "expires_in": result.session.expires_in,
    }


@router.post("/logout", response_model=MessageResponse)
def logout(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """
    NOTE: JWT tokens are stateless — logout sirf client-side token delete karta hai.
    True server-side invalidation ke liye Supabase mein JWT expiry kam karo (≤15 min).
    Dashboard → Auth → JWT Settings → JWT expiry
    """
    sb = get_admin_supabase()
    try:
        user_id: str = current["profile"]["id"]
        sb.auth.admin.sign_out(user_id)
    except Exception as e:
        logger.warning("Sign out attempt failed (non-critical): %s", e)
    return {"message": "Logged out successfully"}