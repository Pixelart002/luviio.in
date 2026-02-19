import logging
import os
import httpx # Beast Mode: Async HTTP client
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- STEP 1: BEAST LEVEL LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("LuviioSystem")

app = FastAPI(title="Luviio.in | AI Powered SPA")

# --- STEP 2: PATHS & TEMPLATES ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.enable_async = True 

# --- STEP 3: MODELS ---
class UIState(BaseModel):
    page_title: str
    nav_items: List[Dict[str, Any]]
    user_status: str = "Studio Access"

# --- STEP 4: ASSET MOUNTING ---
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- STEP 5: AI AUTO-DEBUGGER LOGIC ---
async def get_ai_solution(error_msg: str):
    """
    Mistral AI integration to fetch fixes directly into the console.
    """
    user_id = "Luviio_Beast_Mode"
    # Constructing the URL as requested
    mistral_url = f"https://mistral-ai-three.vercel.app/?id={user_id}&question=Fix this FastAPI/Jinja error: {error_msg}"
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(mistral_url)
            if res.status_code == 200:
                solution = res.text
                print("\n" + "="*50)
                print("🤖 AI DEBUGGER SUGGESTION:")
                print(solution)
                print("="*50 + "\n")
                return solution
    except Exception as e:
        logger.error(f"AI Debugger Failed: {str(e)}")
    return "No AI suggestion available."

# --- STEP 6: ADVANCED EXCEPTION HANDLING (WITH AI) ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_detail = str(exc)
    logger.error(f"SPA Glitch: {error_detail}", exc_info=True)
    
    # Triggering AI Auto-Fix in Background
    ai_fix = await get_ai_solution(error_detail)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Connectivity Issue",
            "detail": error_detail,
            "ai_suggestion": "Check server console for a code snippet fix!",
            "path_searched": TEMPLATE_DIR
        }
    )

# --- STEP 7: STATE-DRIVEN ROUTE ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    try:
        state = UIState(
            page_title="Home | Luviio Luxury Bath",
            nav_items=[
                {"label": "The Studio", "url": "/studio", "active": True},
                {"label": "Materials", "url": "/materials", "active": False}
            ]
        )
        
        state_data = state.model_dump() if hasattr(state, 'model_dump') else state.dict()
        return templates.TemplateResponse("app/pages/index.html", {"request": request, "state": state_data})
    except Exception as e:
        raise e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)