import os
import sys

# ----------------------------------------------------------------
# 🔧 PATH FIX FOR VERCEL (Ye 3 lines magic hain)
# ----------------------------------------------------------------
# Current file (main.py) ki directory nikalo
current_dir = os.path.dirname(os.path.abspath(__file__))
# Us directory ko Python ke search path mein add kar do
if current_dir not in sys.path:
    sys.path.append(current_dir)

# ----------------------------------------------------------------
# AB IMPORTS KAAM KARENGE
# ----------------------------------------------------------------
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# Import secure mail router
# Ab Python ko 'routes' folder mil jayega
from routes.resend_mail import router as mail_router

app = FastAPI()

# 1. Path Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Mount Static & Templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ✅ Connect the router
app.include_router(mail_router)

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home",
        "up_fragment": x_up_target is not None 
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/login.html", {
        "request": request,
        "title": "Login | LUVIIO",
        "up_fragment": x_up_target is not None
    })

@app.get("/waitlist", response_class=HTMLResponse)
async def render_waitlist(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/waitlist.html", {
        "request": request,
        "title": "Join Waitlist | LUVIIO", 
        "active_page": "home",
        "up_fragment": x_up_target is not None 
    })