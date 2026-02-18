import logging
import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# --- Step 1: Beast Level Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("LuviioSystem")

app = FastAPI(title="Luviio.in Advanced System")

# --- Step 2: Strict Path Logic ---
# Hum ensure karenge ki BASE_DIR hamesha 'api' folder ko point kare
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Debugging: Startup par hi check karlo connectivity
def verify_template_structure():
    logger.info(f"Checking connectivity for: {TEMPLATE_DIR}")
    for root, dirs, files in os.walk(TEMPLATE_DIR):
        for file in files:
            # Yeh log humein batayega ki file path 'macros/animation/gsap.html' exist karta hai ya nahi
            rel_path = os.path.relpath(os.path.join(root, file), TEMPLATE_DIR)
            logger.info(f"Connected Template: {rel_path}")

verify_template_structure()

# Jinja2 setup with strict path
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# --- Step 3: Global Logic Injection ---
templates.env.globals.update(now=datetime.now)

# --- Step 4: Asset Mounting ---
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- Step 5: High-End Route Handling ---
@app.get("/")
async def home_route(request: Request):
    try:
        context = {
            "request": request,
            "page_title": "Home | Luviio Beast Mode",
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        # Render check
        return templates.TemplateResponse("app/pages/home.html", context)
    except Exception as e:
        logger.error(f"Render Fail: {str(e)}", exc_info=True)
        # Detailed error for debugging
        return {"error": "Connectivity Issue", "detail": str(e), "path_searched": TEMPLATE_DIR}

@app.get("/docss") # Fixed typo from /docss to /docs
async def documentation_route(request: Request):
    try:
        return templates.TemplateResponse("app/pages/docss.html", {"request": request})
    except Exception as e:
        logger.error(f"Docs fail: {str(e)}")
        return {"error": "Docs not available"}