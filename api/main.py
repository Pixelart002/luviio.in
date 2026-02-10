import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.templating import Jinja2Templates
from .routes.auth import router as auth_router

app = FastAPI()

# 1. Gzip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. Paths & Static Files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# 3. Jinja2 Setup (Global access via app.state)
# Directory: api/templates
app.state.templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# 4. Include Routers
app.include_router(auth_router)

@app.get("/health")
def health_check():
    return {"status": "running"}