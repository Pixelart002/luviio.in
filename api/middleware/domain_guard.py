from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
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
        
        # 2. MAIN DOMAIN REDIRECT (Unpoly Friendly)
        elif any(domain in host for domain in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                target_url = f"https://{AUTH_DOMAIN}{path}"
                
                # 🔥 FIX 1: Unpoly needs 303 status for AJAX redirection
                response = RedirectResponse(url=target_url, status_code=303)
                response.headers["X-Up-Location"] = target_url
                
                # 🔥 FIX 2: Manual CORS Headers (Kyunki ye standard chain bypass karta hai)
                if origin:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                
                return response

        return await call_next(request)