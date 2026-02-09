import os
from fastapi import APIRouter, Request, Header
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter()

# Path set karein (api folder ke andar)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/", response_class=HTMLResponse)
async def get_home(request: Request, x_up_target: str = Header(None)):
    """
    Unpoly Integration: Agar 'X-Up-Target' header hai, 
    toh hum poora layout nahi bhejenge.
    """
    context = {"request": request, "title": "Luviio Portal"}
    
    # Unpoly Fragment handling
    if x_up_target == "#main-content":
        return templates.TemplateResponse("/layout-components/login_macros.html", context)
        
    # Default: Poora page serve karein
    return templates.TemplateResponse("active-layouts/index.html", context)