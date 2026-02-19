import logging
import os
import httpx
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

# --- STEP 2: PATHS & TEMPLATES (No Static) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# Jinja2 Setup
templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.enable_async = True 

# --- STEP 3: STATE MODELS ---
class UIState(BaseModel):
    page_title: str
    nav_items: List[Dict[str, Any]]
    user_status: str = "Studio Access"
    server_time: str = datetime.now().strftime("%H:%M:%S")

# --- STEP 4: AI AUTO-DEBUGGER LOGIC ---
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

# --- STEP 5: ADVANCED EXCEPTION HANDLING ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_detail = str(exc)
    logger.error(f"SPA Glitch: {error_detail}", exc_info=True)
    
    # AI suggestion console pe print hogi
    await get_ai_solution(error_detail)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Logic Error",
            "detail": error_detail,
            "ai_hint": "Check terminal for the AI fix snippet."
        }
    )

# --- STEP 6: STATE-DRIVEN ROUTE ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    try:
        state = UIState(
            page_title="Home | Luviio Luxury",
            nav_items=[
                {"label": "The Studio", "url": "/studio", "active": True},
                {"label": "Materials", "url": "/materials", "active": False}
            ]
        )
        
        # Pydantic state to Dict
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