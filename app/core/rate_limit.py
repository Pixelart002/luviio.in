"""
Global Rate Limiter
===================
Path: app/core/rate_limit.py

The limiter remains process-local (SlowAPI); this module is responsible for
correct client-IP extraction. Forwarded headers are trusted only when the
immediate peer belongs to an explicitly configured trusted proxy.
"""
from ipaddress import ip_address, ip_network

from fastapi import Request
from slowapi import Limiter

from app.core.config import settings


def _peer_is_trusted(request: Request) -> bool:
    peer = request.client.host if request.client else ""
    if not peer:
        return False

    try:
        peer_ip = ip_address(peer)
    except ValueError:
        return False

    for entry in settings.trusted_proxy_ips:
        try:
            if "/" in entry:
                if peer_ip in ip_network(entry, strict=False):
                    return True
            elif peer_ip == ip_address(entry):
                return True
        except ValueError:
            # Invalid deployment configuration must never make an untrusted
            # request trusted.
            continue
    return False


def _get_client_ip(request: Request) -> str:
    # Only consume proxy-supplied identity when the direct peer is trusted.
    if _peer_is_trusted(request):
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            try:
                return str(ip_address(cf_ip.strip()))
            except ValueError:
                pass

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # The left-most value is the original client only when the
            # immediate proxy is trusted and the proxy chain is controlled.
            candidate = forwarded.split(",")[0].strip()
            try:
                return str(ip_address(candidate))
            except ValueError:
                pass

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            try:
                return str(ip_address(real_ip.strip()))
            except ValueError:
                pass

    # Direct peer is the only trusted identity by default.
    return request.client.host if request.client else "unknown"


limiter = Limiter(
    key_func=_get_client_ip,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)
