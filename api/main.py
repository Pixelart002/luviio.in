import os
import sys
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.gzip import GZipMiddleware

# 🔥 FIX 1: Vercel Path Injection (Imports se pehle)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from api.routes.routes import router as luviio_router
from api.routes.cart import router as cart_router
from api.config.ui_config import UI_CONFIG  # Ab yeh Vercel pe nahi phatega!

# Directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# FastAPI Setup
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Luviio.in | Static Version")

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount Static Files
app.mount("/api/static", StaticFiles(directory=STATIC_DIR), name="static")

# 🔥 FIX 2: Pehle templates initialize karo, phir usme config dalo!
templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals['ui_config'] = UI_CONFIG  # Spelling fixed and moved here

# --- AI DEBUGGER ---
async def get_ai_solution(error_msg: str):
    url = f"https://mistral-ai-three.vercel.app/?id=Luviio_Vercel&question=Fix: {error_msg}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url)
            return res.text if res.status_code == 200 else "AI unavailable"
    except:
        return "Debugger Timeout"

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_detail = str(exc)
    ai_fix = await get_ai_solution(error_detail)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": error_detail,
            "ai_suggestion": ai_fix[:200]
        }
    )

# Include Routers
app.include_router(luviio_router)
app.include_router(cart_router)