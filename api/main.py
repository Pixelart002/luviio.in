import os
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

app = FastAPI()

# 1. Path Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Mount Static & Templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 3. Routes
@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO | Verified Markets",
        "active_page": "home"
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("app/pages/login.html", {"request": request})