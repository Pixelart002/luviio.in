import os
from fastapi import APIRouter, Request, Header
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter()

# --- TEMPLATE ENGINE SETUP ---
# BASE_DIR ensure karta hai ki Vercel par paths kabhi crash na hon
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/", response_class=HTMLResponse)
async def test_page(request: Request, x_up_target: str = Header(None)):
    """
    Home Page Route:
    - x_up_target: Unpoly header check karta hai.
    - up_fragment: Jinja2 ko batata hai ki layout extend karna hai ya nahi.
    """
    
    # 1. Define Context Dictionary (Clean way to pass data)
    context = {
        "request": request,
        "title": "LUVIIO | Home",
        "up_fragment": x_up_target is not None, # Unpoly specific flag
        "user": None, # Future: Database se user session yahan aayega
        "active_page": "home"
    }

    # 2. Rendering Decision
    # Agar Unpoly sirf #main-content maang raha hai, toh Jinja wahi handle karega
    return templates.TemplateResponse("pages/home.html", context)