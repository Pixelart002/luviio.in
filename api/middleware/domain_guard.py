from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ 1. CORS HANDSHAKE (MANDATORY)
        # Isse browser ki preflight requests fail nahi hongi
        if request.method == "OPTIONS":
            return await call_next(request)

        # 🔍 Host & Path info
        raw_host = request.url.hostname or ""
        host = raw_host.lower()
        path = request.url.path
        origin = request.headers.get("origin")
        
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAINS = ["luviio.in", "www.luviio.in", "vercel.app"]
        AUTH_ONLY_PATHS = ["/login", "/signup"]

        # 🚀 THE ONLY JOB: Redirect auth traffic from main to subdomain
        # Agar user luviio.in par /login ya /signup mangta hai
        if any(d in host for d in MAIN_DOMAINS) and path in AUTH_ONLY_PATHS:
            target_url = f"https://{AUTH_DOMAIN}{path}"
            
            # 🔥 UNPOLY & CORS COMPATIBILITY
            response = RedirectResponse(url=target_url, status_code=303)
            response.headers["X-Up-Location"] = target_url
            
            if origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Vary"] = "Origin"
            
            return response

        # ✅ BAAKI SAB ALLOWED: No blocking, no /error, no interference
        return await call_next(request)