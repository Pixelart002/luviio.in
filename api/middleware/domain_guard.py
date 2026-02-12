from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ CORS Preflight Fast Pass
        if request.method == "OPTIONS":
            return await call_next(request)

        # 🎯 Clean Host aur Path nikalna
        host = request.url.hostname.lower() if request.url.hostname else ""
        path = request.url.path.rstrip('/') # /login/ ko /login bana dega
        origin = request.headers.get("origin")
        
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAINS = [
            "luviio.in", 
            "www.luviio.in",
            "luviio-qgo2xbkon-pixelart002s-projects.vercel.app"
        ]
        
        # In paths ko strictly redirect karna hai
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + ["/static", "/error"]

        # 1. CASE: Request on AUTH SUBDOMAIN
        if host == AUTH_DOMAIN:
            if not any(path.startswith(p) for p in ALLOWED_AUTH_PATHS):
                return RedirectResponse(url="/error")
        
        # 2. CASE: Request on MAIN DOMAIN (Redirect logic)
        elif any(domain == host for domain in MAIN_DOMAINS) or not host:
            if path in AUTH_ONLY_PATHS:
                target_url = f"https://{AUTH_DOMAIN}{path}"
                
                # 🔥 STRICT FIX: Status 303 + Headers
                response = RedirectResponse(url=target_url, status_code=303)
                response.headers["X-Up-Location"] = target_url # Unpoly fix
                
                if origin:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                
                return response

        return await call_next(request)