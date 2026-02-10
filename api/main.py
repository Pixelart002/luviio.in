import os
from fastapi import FastAPI, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

app = FastAPI()

# Path setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Static & Templates config
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    # Direct logic taaki koi error na aaye
    return templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "LUVIIO - The Trust Layer",
        "active_page": "home"
    })

@app.get("/health")
def health():
    return {"status": "alive"}