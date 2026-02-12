from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        # 🛡️ Settings
        AUTH_DOMAIN = "auth.luviio.in"
        ALLOWED_AUTH_PATHS = ["/login", "/signup", "/static"]

        if AUTH_DOMAIN in host:
            # Check if path is allowed (static files are a must for UI)
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            if not is_allowed:
                raise HTTPException(
                    status_code=403, 
                    detail="Restricted: Domain is limited to authentication."
                )
        
        return await call_next(request)