from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
import os

# Using absolute imports for consistency
from app.core.supabase import SupabaseService 

router = APIRouter()

# Define template directory relative to this file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/")
async def landing_page(request: Request):
    return templates.TemplateResponse("pages/index.html", {
        "request": request,
        "page_title": "Luviio | Redefining Digital Physics"
    })

@router.post("/join-waitlist")
async def join_waitlist(email: str = Form(...)):
    # Optional: Add DB logic here
    # db = SupabaseService.get_client()
    return {"status": "success", "message": "Welcome to the future."}
