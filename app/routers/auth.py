from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from app.supabase_client import get_supabase
from app.dependencies import get_current_user
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
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


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest):
    sb = get_supabase()
    try:
        result = sb.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
            "options": {"data": {"full_name": payload.full_name or ""}},
        })
        if not result.user:
            raise HTTPException(status_code=400, detail="Registration failed")
    except Exception as e:
        msg = str(e)
        if "already registered" in msg.lower() or "already exists" in msg.lower():
            raise HTTPException(status_code=409, detail="Email already registered")
        raise HTTPException(status_code=400, detail="Registration failed")

    return {"message": "Registration successful. Please check your email to confirm your account."}


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest):
    sb = get_supabase()
    try:
        result = sb.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })
        if not result.user or not result.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")

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


@router.post("/refresh")
@limiter.limit("10/minute")
def refresh(request: Request, payload: RefreshRequest):
    sb = get_supabase()
    try:
        result = sb.auth.refresh_session(payload.refresh_token)
        if not result.session:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    return {
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout(current: dict = Depends(get_current_user)):
    sb = get_supabase()
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    return {"message": "Logged out successfully"}