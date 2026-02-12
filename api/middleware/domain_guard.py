from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse, Response

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ 1. FAST PASS FOR CORS PREFLIGHT (OPTIONS)
        # Browser ki purani dushmani khatam karne ke liye
        if request.method == "OPTIONS":
            return await call_next(request)

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

        # 🚀 2. AUTH SUBDOMAIN LOCKDOWN
        if host == AUTH_DOMAIN:
            if not any(path.startswith(p) for p in ALLOWED_AUTH_PATHS):
                return RedirectResponse(url="/error")
        
        # 🚀 3. MAIN DOMAIN REDIRECT (Unpoly + CORS Friendly)
        elif any(domain in host for domain in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                target_url = f"https://{AUTH_DOMAIN}{path}"
                
                # Unpoly needs 303 for cross-domain fragment loading
                response = RedirectResponse(url=target_url, status_code=303)
                
                # Mandatory Unpoly Header
                response.headers["X-Up-Location"] = target_url
                
                # Manual CORS Bridge (Redirect chain bypasses standard CORS middleware)
                if origin:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                    response.headers["Vary"] = "Origin"
                
                return response

        return await call_next(request)