from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse, Response

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ 1. OPTIONS & FAVICON SILENCER
        # Browser ki automatic requests ko pehle hi pass hone do
        if request.method == "OPTIONS" or request.url.path in ["/favicon.ico", "/favicon.png"]:
            return await call_next(request)

        raw_host = request.url.hostname or ""
        host = raw_host.lower()
        path = request.url.path
        origin = request.headers.get("origin")
        
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAINS = ["luviio.in", "www.luviio.in", "vercel.app"]
        
        # Allowed paths strictly for auth domain
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + ["/static", "/error"]

        # 🚀 CASE 1: Request on AUTH SUBDOMAIN
        if host == AUTH_DOMAIN:
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            if not is_allowed:
                return RedirectResponse(url="https://luviio.in/error")
            return await call_next(request)
        
        # 🚀 CASE 2: Request on MAIN DOMAIN
        elif any(d in host for d in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                target_url = f"https://{AUTH_DOMAIN}{path}"
                response = RedirectResponse(url=target_url, status_code=303)
                response.headers["X-Up-Location"] = target_url
                if origin:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                return response

        return await call_next(request)