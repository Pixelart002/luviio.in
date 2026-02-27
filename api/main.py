import os
import sys

# ==========================================
# 🔥 VERCEL & MODULE PATH FIX
# ==========================================
# Yeh ensure karta hai ki 'api' folder ke andar ke modules asani se mil jayein
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# --- ROUTER IMPORTS ---
from api.routes.pages import router as pages_router
from api.routes.cart import router as cart_router

app = FastAPI(
    title="LUVIIO - Modular Bathware Engine",
    description="Premium backend architecture for luxury e-commerce",
    version="2.0.0"
)

# ==========================================
# 📂 STATIC FILES MOUNTING
# ==========================================
# Isse tumhare HTML me /api/static/images/logo.png jaise paths kaam karenge
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.exists(STATIC_DIR):
    app.mount("/api/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    print(f"Warning: Static directory not found at {STATIC_DIR}")

# ==========================================
# 🚀 ROUTER INCLUSION
# ==========================================

# 1. Cart API Router (Pehle API endpoints ko rakhte hain)
app.include_router(cart_router)

# 2. HTML Pages Router (Isme home, login, register sab hai)
app.include_router(pages_router)

# ==========================================
# 🛠️ GLOBAL EXCEPTION HANDLERS (Optional but Recommended)
# ==========================================
@app.on_event("startup")
async def startup_event():
    print("LUVIIO Backend Engine is starting up...")

@app.get("/health")
async def health_check():
    """Vercel monitoring ke liye"""
    return {"status": "online", "engine": "modular_v2"}