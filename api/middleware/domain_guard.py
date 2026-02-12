from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ OPTIONS request ko bypass karo (CORS handshake)
        if request.method == "OPTIONS":
            return await call_next(request)

        # 🔍 Hostname ko clean nikalna
        raw_host = request.url.hostname or ""
        host = raw_host.lower()
        path = request.url.path
        
        AUTH_DOMAIN = "auth.luviio.in"
        # Saare legit domains ki list
        MAIN_DOMAINS = ["luviio.in", "www.luviio.in", "vercel.app"]
        
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + ["/static", "/error"]

        # 1. Agar request AUTH SUBDOMAIN par aayi hai
        if host == AUTH_DOMAIN:
            # Check karo ki path allowed hai ya nahi
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            if not is_allowed:
                # Agar unauthorized path hai (e.g. dashboard), toh error par bhejo
                return RedirectResponse(url="https://luviio.in/error")
            
            # Agar path allowed hai, toh aage badhne do
            return await call_next(request)
        
        # 2. Agar request MAIN DOMAIN par aayi hai
        elif any(d in host for d in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                # Forcefully redirect to AUTH subdomain
                # Absolute URL use karna taaki browser confuse na ho
                target_url = f"https://{AUTH_DOMAIN}{path}"
                return RedirectResponse(url=target_url, status_code=303)

        # 3. Default fallback
        return await call_next(request)