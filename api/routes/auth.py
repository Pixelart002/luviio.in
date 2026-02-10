import os
from fastapi import APIRouter, Request, Header, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
# database.py se wrapper aur client uthayenge
from .database import supabase, db_safe_execute 

router = APIRouter(tags=["Authentication"])

# Path setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/", response_class=HTMLResponse)
@db_safe_execute
async def get_home(request: Request, x_up_target: str = Header(None)):
    """
    Production Home Route: User session check karke home page render karega.
    """
    # Dummy session check (Replace with real Supabase session logic)
    user_session = None 
    
    context = {
        "request": request, 
        "user": user_session, 
        "active_page": "home"
    }

    # Unpoly Fragment handling: Agar sirf content area manga hai
    if x_up_target == "#main-content":
        # Hum ek 'partial' render karenge jo layout ko extend nahi karta
        return templates.TemplateResponse("pages/home_content.html", context)
        
    # Default: Poora master layout serve karein
    return templates.TemplateResponse("active-layouts/index.html", context)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("pages/login.html", {"request": request})