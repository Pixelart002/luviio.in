import logging
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import datetime

# Logger Configuration - Enterprise Standard
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Luviio Advanced")

# Jinja 3.1 Setup
templates = Jinja2Templates(directory="api/templates")

# Injecting global functions (Clean Code)
templates.env.globals.update(now=datetime.now)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Performance & Debug Logging"""
    start_time = datetime.now()
    response = await call_next(request)
    duration = datetime.now() - start_time
    logger.info(f"Path: {request.url.path} | Duration: {duration}")
    return response

@app.get("/")
async def home(request: Request):
    try:
        # Context building
        context = {
            "request": request,
            "status": "online",
            "features": ["GSAP Animations", "Tailwind 3.4", "Jinja 3.1 Macros"]
        }
        return templates.TemplateResponse("app/pages/home.html", context)
    except Exception as e:
        logger.error(f"Render Error: {str(e)}")
        return {"error": "Internal Server Error", "code": 500}