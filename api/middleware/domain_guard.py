from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        # 🛡️ CONFIGURATION
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAINS = [
            "luviio.in", 
            "www.luviio.in",
            "luviio-qgo2xbkon-pixelart002s-projects.vercel.app" # Preview URL
        ]
        
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + ["/static", "/error"]

        # 1. CASE: Request coming from AUTH SUBDOMAIN
        if host == AUTH_DOMAIN:
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            if not is_allowed:
                # Unauthorized path on auth domain -> Troll 404
                return RedirectResponse(url="/error")
        
        # 2. CASE: Request coming from MAIN or PREVIEW Domains
        elif any(domain in host for domain in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                target_url = f"https://{AUTH_DOMAIN}{path}"
                
                # 🔥 UNPOLY FIX: Use 303 status for AJAX-friendly redirects
                response = RedirectResponse(url=target_url, status_code=303)
                
                # 🔥 UNPOLY FIX: Tell Unpoly where the new content is
                response.headers["X-Up-Location"] = target_url
                
                # Ensure CORS headers are present even on redirect
                response.headers["Access-Control-Allow-Origin"] = f"https://{host}"
                response.headers["Access-Control-Allow-Credentials"] = "true"
                
                return response

        # 3. CASE: Fallback
        return await call_next(request)