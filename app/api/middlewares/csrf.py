"""
CSRF protection for browser cookie authentication.

Cookie-authenticated state-changing requests must carry a trusted Origin or
Referer. Bearer-token requests are not subject to this browser-cookie check.
"""
from urllib.parse import urlsplit

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_COOKIE_NAMES = frozenset({"access_token", "refresh_token"})


def _origin_from_referer(referer: str) -> str | None:
    parsed = urlsplit(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _allowed(origin: str) -> bool:
    allowed_origins = settings.cors_origins
    return "*" in allowed_origins or origin in allowed_origins


async def csrf_middleware(request: Request, call_next):
    """Reject cross-site state changes made with Luviio auth cookies."""
    if request.method in _SAFE_METHODS:
        return await call_next(request)

    # API clients using Authorization: Bearer are not exposed to cookie CSRF.
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return await call_next(request)

    cookie_header = request.headers.get("cookie", "")
    has_auth_cookie = any(
        f"{name}=" in cookie_header for name in _COOKIE_NAMES
    )
    if not has_auth_cookie:
        return await call_next(request)

    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        origin = _origin_from_referer(referer) if referer else None

    if origin is None or not _allowed(origin):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "CSRF validation failed."},
        )

    return await call_next(request)
