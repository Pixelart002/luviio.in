import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from .routes.auth import router as auth_router # Import router

app = FastAPI()

# 1. Gzip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. Static Files Mounting
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# 3. Include Routers
app.include_router(auth_router) # Saare auth routes register ho gaye

# Global error handlers ya health checks yahan rakh sakte hain
@app.get("/health")
def health_check():
    return {"status": "running"}