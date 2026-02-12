from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

class AuthIsolationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").lower()
        path = request.url.path
        
        # 🛡️ CONFIG
        AUTH_SUBDOMAIN = "auth.luviio.in"
        MAIN_DOMAIN = "luviio.in"
        # In paths ke liye auth subdomain mandatory hai
        AUTH_PATHS = ["/login", "/signup"]
        # Static files har jagah allowed hain (CSS/JS breaks prevent karne ke liye)
        STATIC_PATHS = ["/static"]

        # Case 1: User is on AUTH SUBDOMAIN
        if host == AUTH_SUBDOMAIN:
            # Allow only auth paths and static files
            is_allowed = any(path.startswith(p) for p in AUTH_PATHS + STATIC_PATHS)
            if not is_allowed:
                # 🛑 Attacker trying to browse dashboard/settings via auth domain
                raise HTTPException(status_code=403, detail="Forbidden: Dedicated Auth Domain.")

        # Case 2: User hits Auth Paths on MAIN DOMAIN (Optional Redirect)
        # Agar koi luviio.in/login par aaye, toh use auth.luviio.in par bhejo
        elif any(path.startswith(p) for p in AUTH_PATHS):
            # Redirecting to secure auth subdomain
            target_url = f"https://{AUTH_SUBDOMAIN}{path}"
            return RedirectResponse(url=target_url)

        return await call_next(request)