import logging
import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Beast Level Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LuviioSystem")

app = FastAPI()

# Absolute path implementation to avoid "Template Not Found" errors
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Static files mounting
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/")
async def home_route(request: Request):
    try:
        return templates.TemplateResponse("app/pages/home.html", {"request": request})
    except Exception as e:
        logger.error(f"Render Fail: {str(e)}")
        return {"error": "Critical Render Error", "status": 500}