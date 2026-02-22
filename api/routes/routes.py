import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Yahan humne 'router' banaya hai, 'app' nahi
router = APIRouter()

# Templates ka path define karna zaroori hai agar route yahan hai
# (Ye path assume karta hai ki tumhara 'templates' folder 'api' folder ke andar ya project root mein hai)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# Agar tumhara Vercel par template path alag hai, toh upar wali line apne hisaab se adjust kar lena
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# FIX: Yahan @app.get ki jagah @router.get aayega!
@router.get("/","home","#", response_class=HTMLResponse)
async def home_route(request: Request):
    return templates.TemplateResponse(
        "app/pages/index.html", 
        {"request": request}
    )