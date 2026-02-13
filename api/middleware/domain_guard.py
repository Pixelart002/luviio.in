from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ 1. OPTIONS FAST-PASS (Handshake Fix)
        # Isse browser ke preflight checks fail nahi honge
        if request.method == "OPTIONS":
            return await call_next(request)

        raw_host = request.url.hostname or ""
        host = raw_host.lower()
        path = request.url.path
        origin = request.headers.get("origin")
        
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAINS = ["luviio.in", "www.luviio.in", "vercel.app"]
        AUTH_ONLY_PATHS = ["/login", "/signup"]

        # 🚀 ONLY ONE JOB: Redirect main domain's auth paths to subdomain
        # Agar user luviio.in/login par hai, toh use auth.luviio.in/login par bhejo
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

        # ✅ BAAKI SAB ALLOWED: Koi blocking nahi, koi /error redirect nahi
        return await call_next(request)