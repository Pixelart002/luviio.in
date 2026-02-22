import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 1. Main Index Route
@router.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    return templates.TemplateResponse(
        "app/pages/index.html", 
        {"request": request}
    )

# 2. Redirect Route (/home se / par bhejne ke liye)
@router.get("/home")
async def redirect_to_index():
    # Status code 301 means "Permanent Redirect"
    return RedirectResponse(url="/", status_code=301)