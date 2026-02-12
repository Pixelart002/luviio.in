from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        AUTH_DOMAIN = "auth.luviio.in"
        # 💡 ERROR route ko hamesha allow karna hai
        ALLOWED_AUTH_PATHS = ["/login", "/signup", "/static", "/error"]

        if AUTH_DOMAIN in host:
            # Check if path is allowed
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            
            if not is_allowed:
                # Security redirect to our custom error page
                return RedirectResponse(url="/error")
        
        return await call_next(request)