# backend/app/api/router.py
from fastapi import APIRouter

# Hamara banaya hua users wala endpoint import kar rahe hain
from app.api.v1.endpoints import users

# Ek master router banaya jo sabko handle karega
api_router = APIRouter()

# Users wale darwaze ko master router mein jod diya
# Isse URL banega: /users/signup
api_router.include_router(users.router, prefix="/users", tags=["Users Authentication"])

# Kal ko jab inventory ya products banayenge, toh wo bhi yahi niche aayenge:
# api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])