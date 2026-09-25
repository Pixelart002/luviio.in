"""Auth Router — Async Standardized Endpoints."""
import logging
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.constants.auth_messages import AuthMessages, AuthSecurityMessages
from app.core.dependencies import get_current_user
from app.domains.auth.mfa import (
    MFAError,
    enroll_totp,
    get_verified_totp_factor_id,
    list_factors,
    reset_pending_totp,
)
from app.domains.auth.mfa import (
    challenge as mfa_challenge,
)
from app.domains.auth.mfa import (
    unenroll as mfa_unenroll,
)
from app.domains.auth.mfa import (
    verify as mfa_verify,
)
from app.domains.auth.mfa_schemas import MFAEnrollRequest, MFAUnenrollRequest, MFAVerifyRequest
from app.domains.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.domains.auth.service import AuthService
from app.utils.response import success_response

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["Auth"])

_REFRESH_COOKIE_KWARGS = dict(key="refresh_token", httponly=True, secure=True, samesite="none", path="/api/v1/auth")
_LEGACY_ACCESS_COOKIE_KWARGS = dict(key="access_token", secure=True, httponly=True, samesite="none", path="/api/v1")
_ACCESS_COOKIE_MAX_AGE = 60 * 60
_REFRESH_COOKIE_MAX_AGE = 7 * 24 * 60 * 60


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
        request.state.actions.extend([f"Identity verified -> UID: {session_data['user_id'][:8]}...", "Issued secure HttpOnly auth cookies"])
    response.set_cookie(**_REFRESH_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=_REFRESH_COOKIE_MAX_AGE)
    # Access tokens are returned to the SPA for in-memory Authorization headers only.
    # The browser must not persist a second authentication token in an auth cookie.
    response.delete_cookie(**_LEGACY_ACCESS_COOKIE_KWARGS)
    data = {"access_token": session_data["access_token"], "token_type": "bearer", "expires_in": session_data["expires_in"], "user": {"id": session_data["user_id"], "email": session_data["email"]}}
    return success_response(data=data)


@router.post("/refresh", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(None)):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Intercepted session refresh cookie")
    if not refresh_token:
        response.delete_cookie(**_REFRESH_COOKIE_KWARGS)
        response.delete_cookie(**_LEGACY_ACCESS_COOKIE_KWARGS)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=AuthSecurityMessages.INVALID_REFRESH_TOKEN)
    try:
        session_data = await AuthService().refresh_user_session(refresh_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            response.delete_cookie(**_REFRESH_COOKIE_KWARGS)
            response.delete_cookie(**_LEGACY_ACCESS_COOKIE_KWARGS)
        raise
    if hasattr(request.state, "actions"):
        request.state.actions.append("Session successfully refreshed & prolonged")
    response.set_cookie(**_REFRESH_COOKIE_KWARGS, value=session_data["refresh_token"], max_age=_REFRESH_COOKIE_MAX_AGE)
    response.delete_cookie(**_LEGACY_ACCESS_COOKIE_KWARGS)
    return success_response(data={"access_token": session_data["access_token"], "token_type": "bearer", "expires_in": session_data["expires_in"]})


@router.get("/mfa/status", status_code=status.HTTP_200_OK)
async def mfa_status(current: dict[str, Any] = Depends(get_current_user)):
    try:
        factors = await list_factors(current["access_token"])
    except MFAError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return success_response(
        data={
            "aal": current.get("aal", "aal1"),
            "factors": factors,
            "privileged_mfa_required": (current.get("profile") or {}).get("role") != "customer",
        },
        message="MFA status retrieved.",
    )


@router.post("/mfa/enroll", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def mfa_enroll(
    request: Request,
    payload: MFAEnrollRequest,
    current: dict[str, Any] = Depends(get_current_user),
):
    role = (current.get("profile") or {}).get("role", "customer")
    if role == "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA enrollment is restricted to staff accounts.")
    try:
        data = await enroll_totp(current["access_token"], payload.friendly_name)
    except MFAError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if hasattr(request.state, "actions"):
        request.state.actions.append("Started TOTP MFA enrollment for privileged account")
    return success_response(data=data, message="MFA enrollment started. Scan the QR code and verify it.")


@router.post("/mfa/verify", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def mfa_verify_code(
    request: Request,
    response: Response,
    payload: MFAVerifyRequest,
    current: dict[str, Any] = Depends(get_current_user),
):
    try:
        factor_id = await get_verified_totp_factor_id(current["access_token"])
        challenge_data = await mfa_challenge(current["access_token"], factor_id)
        challenge_id = str(challenge_data.get("id") or "")
        if not challenge_id:
            raise MFAError("MFA challenge could not be created.")
        session_data = await mfa_verify(
            current["access_token"],
            factor_id,
            challenge_id,
            payload.code,
        )
    except MFAError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    access_token = session_data.get("access_token")
    refresh_token = session_data.get("refresh_token")
    if access_token:
        response.delete_cookie(**_LEGACY_ACCESS_COOKIE_KWARGS)
    if refresh_token:
        response.set_cookie(**_REFRESH_COOKIE_KWARGS, value=refresh_token, max_age=_REFRESH_COOKIE_MAX_AGE)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Privileged MFA challenge verified -> AAL2 session issued")
    return success_response(
        data={
            "access_token": access_token,
            "token_type": session_data.get("token_type", "bearer"),
            "expires_in": session_data.get("expires_in"),
            "aal": "aal2",
        },
        message="MFA verified successfully.",
    )


@router.post("/mfa/reset-pending", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def mfa_reset_pending(
    request: Request,
    payload: MFAUnenrollRequest,
    current: dict[str, Any] = Depends(get_current_user),
):
    role = (current.get("profile") or {}).get("role", "customer")
    if role == "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA enrollment recovery is restricted to staff accounts.")
    try:
        data = await reset_pending_totp(current["access_token"], payload.factor_id)
    except MFAError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if hasattr(request.state, "actions"):
        request.state.actions.append("Removed unverified TOTP factor so privileged enrollment can restart")
    return success_response(data=data, message="Pending MFA enrollment removed. You can start a new setup.")


@router.post("/mfa/unenroll", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def mfa_unenroll_endpoint(
    request: Request,
    payload: MFAUnenrollRequest,
    current: dict[str, Any] = Depends(get_current_user),
):
    try:
        factors = await list_factors(current["access_token"])
    except MFAError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    factor = next(
        (item for item in factors.get("all", []) if item.get("id") == payload.factor_id),
        None,
    )
    if not factor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MFA factor not found.")

    is_verified = factor.get("status") == "verified"
    if is_verified and current.get("aal", "aal1") != "aal2":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AAL2 verification required to remove a verified MFA factor.",
        )

    try:
        data = await mfa_unenroll(current["access_token"], payload.factor_id)
    except MFAError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if hasattr(request.state, "actions"):
        action = "Privileged MFA factor unenrolled after AAL2 verification" if is_verified else "Pending privileged MFA enrollment reset"
        request.state.actions.append(action)
    return success_response(data=data, message="MFA factor removed.")


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, refresh_token: str | None = Cookie(None)):
    if hasattr(request.state, "actions"):
        request.state.actions.append("Executing user sign-out sequence")
    await AuthService().logout_user(refresh_token)
    response.delete_cookie(**_REFRESH_COOKIE_KWARGS)
    response.delete_cookie(**_ACCESS_COOKIE_KWARGS)
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
