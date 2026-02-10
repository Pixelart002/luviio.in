import os
from fastapi import APIRouter, Request, Header
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
# Aapka banaya hua database wrapper
from .database import db_safe_execute 

router = APIRouter()

# --- TEMPLATE ENGINE SETUP ---
# BASE_DIR ensures paths work on Local and Vercel
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/", response_class=HTMLResponse)
@db_safe_execute
async def get_home(request: Request, x_up_target: str = Header(None)):
    """
    Jinja2 Connection Logic:
    1. 'user' pass hoga header.html macro ke liye.
    2. 'active_page' handle karega nav highlight.
    3. 'x_up_target' handle karega Unpoly fragment swaps.
    """
    context = {
        "request": request,
        "title": "LUVIIO | Home",
        "user": None, # Future mein Supabase session yahan aayega
        "active_page": "home"
    }

    # Case A: Unpoly sirf #main-content maang raha hai
    if x_up_target == "#main-content":
        # Yahan hum 'pages/home.html' bhejenge jo base extend nahi karta
        return templates.TemplateResponse("pages/home_partial.html", context)

    # Case B: Direct visit ya Full Page Refresh
    return templates.TemplateResponse("active-layouts/index.html", context)