from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

# Import router as requested
from routers.public import router as public_router

app = FastAPI(title="Luviio Platform", docs_url=None, redoc_url=None)

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure static folder exists
static_path = os.path.join(BASE_DIR, "static")
os.makedirs(static_path, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Include public router
app.include_router(public_router)

@app.on_event("startup")
async def startup_event():
    print("Luviio Engine: INITIALIZED")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}