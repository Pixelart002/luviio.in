"""
Global Rate Limiter
===================
Path: app/core/rate_limit.py
"""
from fastapi import Request
from slowapi import Limiter
from app.core.config import settings

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded: return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip: return real_ip.strip()

    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip: return cf_ip.strip()

    return request.client.host if request.client else "unknown"

limiter = Limiter(
    key_func=_get_client_ip,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)