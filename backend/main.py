# backend/main.py
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 🚀 NAYA IMPORT: Hamara master router yahan import kiya
from app.api.router import api_router

# 1. Rate Limiter Setup (User ke IP address se track karega)
limiter = Limiter(key_func=get_remote_address)

# 2. FastAPI App Initialization
app = FastAPI(title="Luviio Enterprise API")

# Rate Limiter ko app ke sath jodna
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 3. CORS Setup (Taaki Vercel wala Next.js frontend is API se baat kar sake)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://luviio.in", "https://www.luviio.in"], # Apne Vercel domains yahan add kiye
    allow_credentials=True, # COOKIES (JWT) allow karne ke liye yeh TRUE hona zaroori hai!
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Supabase Database Connection
# Vercel ya Server ke environment variables se keys uthayega
SB_URL = os.getenv("SB_URL", "")
SB_SERVICE_ROLE_KEY = os.getenv("SB_SERVICE_ROLE_KEY", "")

# Agar keys nahi mili toh server start hi nahi hoga (Strict fail-safe)
if not SB_URL or not SB_SERVICE_ROLE_KEY:
    print("⚠️ WARNING: Supabase Environment Variables missing!")

# Hum Service Role Key use kar rahe hain kyunki Auth hum khud manage karenge (Bypass RLS)
if SB_URL and SB_SERVICE_ROLE_KEY:
    supabase: Client = create_client(SB_URL, SB_SERVICE_ROLE_KEY)
else:
    supabase = None

# 🚀 NAYI WIRING: Master router ko FastAPI app ke sath jod diya
# 'prefix="/api/v1"' lagane se saare URLs automatically standard ho jayenge
app.include_router(api_router, prefix="/api/v1")

# 5. Health Check Endpoint (Test karne ke liye)
@app.get("/")
@limiter.limit("5/minute") # Rate Limit: Ek IP se 1 minute mein max 5 requests
async def root(request: Request):
    return {
        "status": "online",
        "message": "Luviio FastAPI Engine is running!",
        "database": "Connected" if supabase else "Disconnected"
    }