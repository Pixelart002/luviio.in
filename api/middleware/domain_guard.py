from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ 1. CORS PREFLIGHT FAST-PASS
        # Browser handshake ko block nahi hone dena
        if request.method == "OPTIONS":
            return await call_next(request)

        # 🔍 CLEAN HOST & PATH
        raw_host = request.url.hostname or ""
        host = raw_host.lower()
        path = request.url.path
        origin = request.headers.get("origin")
        
        # CONFIGURATION
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAINS = ["luviio.in", "www.luviio.in", "vercel.app"]
        
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        # Auth domain par sirf ye paths allowed hain
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + ["/static", "/error"]

        # 🚀 CASE 1: Request is on AUTH SUBDOMAIN (auth.luviio.in)
        if host == AUTH_DOMAIN:
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            if not is_allowed:
                # Agar user auth domain par reh kar dashboard ya home try kare
                # Toh use wapas main domain ke error page par bhej do
                return RedirectResponse(url="https://luviio.in/error")
            
            return await call_next(request)
        
        # 🚀 CASE 2: Request is on MAIN DOMAIN (luviio.in / vercel preview)
        elif any(d in host for d in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                # Forcefully redirect /login aur /signup to the dedicated Auth Subdomain
                target_url = f"https://{AUTH_DOMAIN}{path}"
                
                # 🔥 THE UNPOLY & CORS FIX
                response = RedirectResponse(url=target_url, status_code=303)
                response.headers["X-Up-Location"] = target_url
                
                # Manual CORS Bridge (Kyunki direct return middleware chain bypass karta hai)
                if origin:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                    response.headers["Vary"] = "Origin"
                
                return response

        # 🚀 CASE 3: DEFAULT FALLBACK
        return await call_next(request)