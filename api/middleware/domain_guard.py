from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse, Response

class AuthDomainGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # ⚡ 1. MANDATORY CORS PREFLIGHT FIX
        # Agar OPTIONS request hai, toh direct call_next ko bhej do bina logic ke
        if request.method == "OPTIONS":
            return await call_next(request)

        # 🔍 Host & Path Extraction
        raw_host = request.url.hostname or ""
        host = raw_host.lower()
        path = request.url.path
        origin = request.headers.get("origin")
        
        AUTH_DOMAIN = "auth.luviio.in"
        MAIN_DOMAINS = ["luviio.in", "www.luviio.in", "vercel.app"]
        
        # 🛡️ WHITELIST: In paths ko auth domain par kabhi block nahi karna
        AUTH_ONLY_PATHS = ["/login", "/signup"]
        # Favicon aur common assets ko add kiya taaki faltoo entries na aayein
        ALLOWED_AUTH_PATHS = AUTH_ONLY_PATHS + [
            "/static", "/error", "/favicon.ico", "/favicon.png", "/robots.txt"
        ]

        # 🚀 CASE 1: Request on AUTH SUBDOMAIN
        if host == AUTH_DOMAIN:
            is_allowed = any(path.startswith(p) for p in ALLOWED_AUTH_PATHS)
            if not is_allowed:
                # Agar koi galti se dashboard ya home try kare
                return RedirectResponse(url="https://luviio.in/error")
            
            return await call_next(request)
        
        # 🚀 CASE 2: Request on MAIN DOMAIN (Redirect to Subdomain)
        elif any(d in host for d in MAIN_DOMAINS):
            if path in AUTH_ONLY_PATHS:
                target_url = f"https://{AUTH_DOMAIN}{path}"
                
                # Unpoly & CORS Friendly Redirect
                response = RedirectResponse(url=target_url, status_code=303)
                response.headers["X-Up-Location"] = target_url
                
                if origin:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                
                return response

        return await call_next(request)