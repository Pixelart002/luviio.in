import os
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- CONFIG & PATHS ---
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
    footer_about: str = "Architecture for the most private spaces of your life."  # ✅ Added missing field
    server_time: str = datetime.now().strftime("%H:%M:%S")

# --- AI DEBUGGER ---
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
    ai_fix = await get_ai_solution(error_detail)
    
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": error_detail,
            "ai_suggestion": ai_fix[:200]
        }
    )

# --- HELPER FUNCTION FOR STATE ---
def get_base_state():
    """Returns base state dictionary with all required fields"""
    return {
        "page_title": "Home | Luviio Luxury Studio",
        "nav_items": [
            {"label": "The Studio", "url": "/studio", "active": True},
            {"label": "Materials", "url": "/materials", "active": False},
            {"label": "Projects", "url": "/projects", "active": False},
            {"label": "Journal", "url": "/journal", "active": False}
        ],
        "sidebar_categories": [
            {"label": "Ceramics", "url": "/ceramics"},
            {"label": "Water Systems", "url": "/water"},
            {"label": "Stone Collection", "url": "/stone"},
            {"label": "Bath Fixtures", "url": "/fixtures"}
        ],
        "footer_sections": [
            {
                "title": "Studio",
                "links": [
                    {"label": "About", "url": "/about"},
                    {"label": "Philosophy", "url": "/philosophy"},
                    {"label": "Team", "url": "/team"}
                ]
            },
            {
                "title": "Collections",
                "links": [
                    {"label": "Ceramics", "url": "/ceramics"},
                    {"label": "Water", "url": "/water"},
                    {"label": "Stone", "url": "/stone"}
                ]
            },
            {
                "title": "Connect",
                "links": [
                    {"label": "Instagram", "url": "https://instagram.com/luviio"},
                    {"label": "LinkedIn", "url": "https://linkedin.com/company/luviio"},
                    {"label": "Contact", "url": "/contact"}
                ]
            }
        ],
        "featured_material": {
            "name": "Arctic Matte Stone",
            "url": "/materials/arctic-stone"
        },
        "user_status": "Studio Access",
        "footer_about": "Architecture for the most private spaces of your life.",
        "server_time": datetime.now().strftime("%H:%M:%S")
    }

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    """Home page with complete state"""
    try:
        # Using dictionary approach for maximum compatibility
        state = get_base_state()
        
        return templates.TemplateResponse(
            "app/pages/index.html", 
            {
                "request": request, 
                "state": state  # ✅ Plain dictionary, no model_dump() needed
            }
        )
    except Exception as e:
        # Fallback minimal state if something goes wrong
        fallback_state = {
            "nav_items": [{"label": "Home", "url": "/", "active": True}],
            "sidebar_categories": [],
            "footer_sections": [],
            "user_status": "Studio Access",
            "footer_about": "Luviio Studio",
            "page_title": "Luviio"
        }
        return templates.TemplateResponse(
            "app/pages/index.html",
            {"request": request, "state": fallback_state}
        )

@app.get("/health")
async def health_check():
    """Health check endpoint for Vercel"""
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "environment": "vercel" if os.getenv("VERCEL") else "development"
    }

@app.get("/debug/state")
async def debug_state(request: Request):
    """Debug endpoint to verify state is working"""
    state = get_base_state()
    return JSONResponse({
        "status": "success",
        "state_keys": list(state.keys()),
        "nav_items_count": len(state["nav_items"]),
        "footer_sections_count": len(state["footer_sections"])
    })

# --- FOR LOCAL DEVELOPMENT ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)