from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        # 🛡️ CONFIGURATION
        AUTH_DOMAIN = "auth.luviio.in"
        # Static files zaroori hain taaki CSS/JS load ho sake
        ALLOWED_AUTH_PATHS = ["/login", "/signup", "/static"]

        # 1. Agar request auth subdomain se aa rahi hai
        if host == AUTH_DOMAIN:
            # Check if current path is allowed
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            
            if not is_allowed:
                # 🛑 Block attacker trying to access dashboard/api via auth domain
                raise HTTPException(
                    status_code=403, 
                    detail="Security Violation: This domain is restricted to authentication only."
                )
        
        # 2. (Optional Logic) Agar koi main domain se login/signup par aaye, 
        # toh use yahan block ya redirect kar sakte ho.

        return await call_next(request)