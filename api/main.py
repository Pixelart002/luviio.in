import os
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI(title="Luviio.in | Static Version")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.enable_async = True

# --- AI DEBUGGER (optional, can be removed if not needed) ---
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

# --- IMPORT ROUTES ---
# This connects the routes.py file to main.py
from routes import router as app_router
app.include_router(app_router)

# --- ROUTES (main route can stay here or move to routes.py) ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    # No state needed – templates are static
    return templates.TemplateResponse(
        "app/pages/index.html", 
        {"request": request}
    )