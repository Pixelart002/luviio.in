import logging
import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# --- Step 1: Initialize Beast Level Logging ---
# Professional logging setup for enterprise auditing
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("LuviioSystem")

app = FastAPI(title="Luviio.in Advanced System")

# --- Step 2: Resource Path Configuration ---
# Absolute paths ensure the system never fails regardless of where it's deployed
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)

# --- Step 3: Global Logic Injection (The Fix) ---
# Injecting 'now' into Jinja 3.1 globals so it's available in all macros/templates
templates.env.globals.update(now=datetime.now)

# --- Step 4: Mounting Static Assets ---
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning("Static directory not found. UI might look broken.")

# --- Step 5: Advanced Route Handling ---
@app.get("/")
async def home_route(request: Request):
    """
    Serves the main landing page with strict error checking.
    Hierarchy: Request -> Template Engine -> Response
    """
    try:
        # Business logic goes here
        context = {
            "request": request,
            "page_title": "Home | Luviio Beast Mode",
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        logger.info(f"Successfully rendered home page for {request.client.host}")
        return templates.TemplateResponse("app/pages/home.html", context)

    except Exception as e:
        # Detailed error logging for rapid debugging
        logger.critical(f"Critical Render Failure: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": "A system-level rendering error occurred.",
            "trace": str(e) if app.debug else "Contact Admin"
        }

# --- Documentation Component ---
@app.get("/docs")
async def documentation_route(request: Request):
    try:
        return templates.TemplateResponse("app/pages/docs.html", {"request": request})
    except Exception as e:
        logger.error(f"Docs fail: {str(e)}")
        return {"error": "Docs not available"}