import logging
import os
import httpx
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- STEP 1: BEAST LEVEL LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("LuviioSystem")

app = FastAPI(title="Luviio.in | Pure Logic SPA")

# --- STEP 2: PERFORMANCE MIDDLEWARE ---
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"Route: {request.url.path} | Time: {process_time:.4f}s")
    return response

# --- STEP 3: PATHS & TEMPLATES (No Static) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.enable_async = True 

# --- STEP 4: STATE MODELS (Strictly Typed) ---
class UIState(BaseModel):
    page_title: str
    nav_items: List[Dict[str, Any]]
    sidebar_categories: List[Dict[str, Any]]
    featured_material: Optional[Dict[str, Any]] = None
    footer_sections: List[Dict[str, Any]]
    user_status: str = "Studio Access"
    server_time: str = datetime.now().strftime("%H:%M:%S")

# --- STEP 5: AI AUTO-DEBUGGER LOGIC ---
async def get_ai_solution(error_msg: str):
    user_id = "Luviio_Beast_Mode"
    mistral_url = f"https://mistral-ai-three.vercel.app/?id={user_id}&question=Fix this FastAPI/Jinja error: {error_msg}"
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(mistral_url)
            if res.status_code == 200:
                print("\n" + "="*50)
                print("🤖 AI DEBUGGER SUGGESTION:")
                print(res.text)
                print("="*50 + "\n")
                return res.text
    except Exception as e:
        logger.error(f"AI Debugger Failed: {str(e)}")
    return "No AI suggestion available."

# --- STEP 6: ADVANCED EXCEPTION HANDLING ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_detail = str(exc)
    logger.error(f"SPA Glitch: {error_detail}", exc_info=True)
    
    # AI suggestion console pe print hogi
    ai_fix = await get_ai_solution(error_detail)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Logic Error",
            "detail": error_detail,
            "ai_fix_preview": ai_fix[:100] + "..." if ai_fix else "Check console.",
            "hint": "Check terminal for the AI fix snippet."
        }
    )

# --- STEP 7: STATE-DRIVEN ROUTE (FIXED STATE) ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    try:
        # BEAST FIX: Ensuring all keys expected by macros are present
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
            # Always providing this prevents the 'no attribute' error
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
        
        state_data = state.model_dump() if hasattr(state, 'model_dump') else state.dict()
        
        return templates.TemplateResponse(
            "app/pages/index.html", 
            {"request": request, "state": state_data}
        )
    except Exception as e:
        raise e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)