"""
Master API Router — Enterprise Grade
====================================
Path: app/api/v1/api.py

Combines all v1 routers into a single master router.
"""
from fastapi import APIRouter

from app.api.v1.routers import (
    health,       # 🔥 NEW: Health & Readiness checks
    auth, 
    users, 
    products, 
    orders, 
    payments, 
    push, 
    cart, 
    invoice, 
    admin_verify
)

api_router = APIRouter()

# ── SYSTEM ROUTES ─────────────────────────────────────────────────────────────
api_router.include_router(health.router)

# ── DOMAIN ROUTES ─────────────────────────────────────────────────────────────
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(products.router)
api_router.include_router(orders.router)
api_router.include_router(payments.router)
api_router.include_router(push.router)
api_router.include_router(admin_verify.router)
api_router.include_router(cart.router)
api_router.include_router(invoice.router)
api_router.include_router(settings.router)