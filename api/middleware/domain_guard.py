from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ FAST PASS FOR OPTIONS (Preflight Fix)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Robust hostname detection
        host = request.url.hostname.lower() if request.url.hostname else ""
        path = request.url.path
        origin = request.headers.get("origin")
        
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
        
        # 2. MAIN DOMAIN TO AUTH REDIRECT
        elif any(domain in host for domain in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                target_url = f"https://{AUTH_DOMAIN}{path}"
                
                # 303 Status is critical for AJAX/Unpoly
                response = RedirectResponse(url=target_url, status_code=303)
                
                # Headers for Unpoly to handle cross-origin transition
                response.headers["X-Up-Location"] = target_url
                
                # Manual CORS Headers for the redirect response
                if origin:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                    response.headers["Vary"] = "Origin"
                
                return response

        return await call_next(request)