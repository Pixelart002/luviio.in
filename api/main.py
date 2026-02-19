import os
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- CONFIG & PATHS ---
# Vercel uses a serverless environment; absolute paths are safer.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI(title="Luviio.in | Vercel Optimized")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.enable_async = True 

# --- MODELS ---
class UIState(BaseModel):
    page_title: str
    nav_items: List[Dict[str, Any]]
    sidebar_categories: List[Dict[str, Any]]
    footer_sections: List[Dict[str, Any]]
    featured_material: Optional[Dict[str, Any]] = None
    user_status: str = "Studio Access"
    server_time: str = datetime.now().strftime("%H:%M:%S")

# --- AI DEBUGGER (Lean Version) ---
async def get_ai_solution(error_msg: str):
    """Silent AI solution fetch for serverless logs."""
    url = f"https://mistral-ai-three.vercel.app/?id=Luviio_Vercel&question=Fix: {error_msg}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url)
            return res.text if res.status_code == 200 else "AI unavailable"
    except:
        return "Debugger Timeout"

# --- EXCEPTION HANDLING ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_detail = str(exc)
    # AI logic runs in the background to avoid blocking the response
    ai_fix = await get_ai_solution(error_detail)
    
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": error_detail,
            "ai_suggestion": ai_fix[:200]  # Keep it short for the response
        }
    )

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    # Pure State-Driven Logic
    state = UIState(
        page_title="Home | Luviio Luxury Studio",
        nav_items=[
            {"label": "The Studio", "url": "/studio", "active": True},
            {"label": "Materials", "url": "/materials", "active": False}
        ],
        sidebar_categories=[
            {"label": "Ceramics", "url": "/ceramics"},
            {"label": "Water Systems", "url": "/water"}
        ],
        featured_material={
            "name": "Arctic Matte Stone",
            "url": "/materials/arctic-stone"
        },
        footer_sections=[
            {
                "title": "Resources",
                "links": [{"label": "Gallery", "url": "/gallery"}]
            }
        ]
    )
    
    return templates.TemplateResponse(
        "app/pages/index.html", 
        {"request": request, "state": state.model_dump()}
    )

# NOTE: No uvicorn.run() block. Vercel handles the entry point via the 'app' object.