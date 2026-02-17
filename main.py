from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

# Absolute imports are preferred in production packages
from app.routers import public 

app = FastAPI(title="Luviio Platform", docs_url=None, redoc_url=None)

# Get the base directory of the app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Mount Static Files (CSS/JS)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Include Routers
app.include_router(public.router)

@app.on_event("startup")
async def startup_event():
    print("Luviio Engine: INITIALIZED")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
