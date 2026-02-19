import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
import os

from api.routes import home   # import your routers
from api.config import settings
from api.utils.error_handlers import global_exception_handler
from api.utils.logging_config import setup_logging

# Setup structured logging
setup_logging(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Jinja2 templates with macros directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
# Expose templates to other modules (optional)
import api.routes.home
api.routes.home.templates = templates

app = FastAPI(title="Luviio.in", debug=settings.DEBUG)

# Register exception handler
app.add_exception_handler(Exception, global_exception_handler)

# Include routers
app.include_router(home.router)

# Optional: health check
@app.get("/health")
async def health():
    return {"status": "ok"}