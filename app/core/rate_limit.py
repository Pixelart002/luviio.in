"""
Global Rate Limiter (Anti-Spoofing)
===================================
Path: app/core/rate_limit.py
"""
from fastapi import Request
from slowapi import Limiter
from app.core.config import settings

def _get_client_ip(request: Request) -> str:
    """
    Hardened IP Extraction. 
    Prioritizes secure CDN headers over easily spoofable client headers.
    """
    # 1. Cloudflare explicitly strips and sets this, cannot be spoofed by client
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip: return cf_ip.strip()

    # 2. AWS/Nginx/Koyeb Load Balancers set this securely
    real_ip = request.headers.get("X-Real-IP")
    if real_ip: return real_ip.strip()

    # 3. Standard proxy header (Can be spoofed, used as fallback)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded: return forwarded.split(",")[0].strip()

    # 4. Direct socket connection
    return request.client.host if request.client else "127.0.0.1"

limiter = Limiter(
    key_func=_get_client_ip,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)