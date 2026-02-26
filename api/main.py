import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.gzip import GZipMiddleware



from api.routes.routes import router as luviio_router
from api.routes.cart import router as cart_router
from config.ui_config import UI_CONFIG





BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
# 2. Static directory ka path define karo:
STATIC_DIR = os.path.join(BASE_DIR, "static")


template.env.globals['ui_config'] = UI_CONFIG


limiter = Limiter(key_func=get_remote_address)


app = FastAPI(title="Luviio.in | Static Version")

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded,_rate_limit_exceeded_handler)





# 3. Yahan StaticFiles ko mount karo:
app.mount("/api/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)



# --- AI DEBUGGER (optional) ---
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

app.include_router(luviio_router)
app.include_router(cart_router)