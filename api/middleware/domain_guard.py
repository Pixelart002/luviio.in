from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAINS = [
            "luviio.in", 
            "www.luviio.in",
            "luviio-qgo2xbkon-pixelart002s-projects.vercel.app"
        ]
        
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + ["/static", "/error"]

        # 1. AUTH SUBDOMAIN LOCKDOWN
        if host == AUTH_DOMAIN:
            if not any(path.startswith(p) for p in ALLOWED_AUTH_PATHS):
                return RedirectResponse(url="/error")
        
        # 2. MAIN DOMAIN REDIRECT (Unpoly Friendly)
        elif any(domain in host for domain in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                target_url = f"https://{AUTH_DOMAIN}{path}"
                
                # 🔥 FIX: Unpoly needs 303 for AJAX redirects
                response = RedirectResponse(url=target_url, status_code=303)
                response.headers["X-Up-Location"] = target_url
                return response

        return await call_next(request)