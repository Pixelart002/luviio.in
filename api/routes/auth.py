import os
from fastapi import APIRouter, Request, Header
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from .database import db_safe_execute 

router = APIRouter()

# --- TEMPLATE PATH FIX ---
# auth.py routes folder mein hai, isliye 2 baar dirname kiya
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/", response_class=HTMLResponse)
@db_safe_execute
async def get_home(request: Request, x_up_target: str = Header(None)):
    context = {
        "request": request,
        "user": None,
        "active_page": "home",
        "title": "LUVIIO | Live"
    }

    # FIX: Leading slash '/' kabhi nahi lagana path mein
    if x_up_target == "#main-content":
        return templates.TemplateResponse("macros/components/header.html", context)

    return templates.TemplateResponse("active-layouts/index.html", context)