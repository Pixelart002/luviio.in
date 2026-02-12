from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 🛡️ CONFIGURATION
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAIN = "luviio.in" # Aapka primary domain
        
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        # Paths jo sirf auth domain par hone chahiye
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        # Paths jo auth domain par allowed hain (static files zaroori hain)
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + ["/static", "/error"]

        # 1. CASE: User is on AUTH SUBDOMAIN (auth.luviio.in)
        if AUTH_DOMAIN in host:
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            if not is_allowed:
                # Agar dashboard ya kuch aur try kare, toh troll 404 page
                return RedirectResponse(url="/error")
        
        # 2. CASE: User is on MAIN DOMAIN (luviio.in)
        else:
            # Agar koi main domain se login/signup par jaane ki koshish kare
            if path in AUTH_ONLY_PATHS:
                # Redirect to the dedicated Auth Subdomain
                # window.location.origin bypass karke absolute URL use kar rahe hain
                target_url = f"https://{AUTH_DOMAIN}{path}"
                return RedirectResponse(url=target_url)

        return await call_next(request)