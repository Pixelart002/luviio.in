from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 🛡️ CONFIGURATION
        AUTH_DOMAIN = "auth.luviio.in"
        
        # Multiple Main Domains (Production + Vercel Previews)
        MAIN_DOMAINS = [
            "luviio.in", 
            "www.luviio.in",
            "luviio-qgo2xbkon-pixelart002s-projects.vercel.app" # Added your preview URL
        ]
        
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        # Paths strictly for auth subdomain
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        # Allowed paths on auth subdomain (including static assets for UI)
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + ["/static", "/error"]

        # 1. CASE: Request coming from AUTH SUBDOMAIN
        if host == AUTH_DOMAIN:
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            if not is_allowed:
                # Security redirect for unauthorized paths on auth domain
                return RedirectResponse(url="/error")
        
        # 2. CASE: Request coming from MAIN or PREVIEW Domains
        elif any(domain in host for domain in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                # Strictly redirect /login or /signup to the Auth Subdomain
                target_url = f"https://{AUTH_DOMAIN}{path}"
                return RedirectResponse(url=target_url)

        # 3. CASE: Fallback (If someone hits the raw Vercel URL directly)
        # We allow them to browse, but login/signup will still trigger Case 2
        return await call_next(request)