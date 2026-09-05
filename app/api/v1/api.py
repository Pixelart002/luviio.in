"""
Master API Router — Enterprise Grade
====================================
Path: app/api/v1/api.py

Composes the versioned HTTP surface. Domain routers live in their owning
vertical slices; infrastructure endpoints are composed separately.
"""
from fastapi import APIRouter

from app.infrastructure.health.router import router as health_router
from app.domains.auth.router import router as auth_router
from app.domains.users.router import router as users_router
from app.domains.products.router import router as products_router
from app.domains.cart.router import router as cart_router
from app.domains.orders.router import router as orders_router
from app.domains.payments.router import router as payments_router
from app.domains.notifications.router import router as push_router
from app.domains.settings.router import router as settings_router
from app.domains.admin.router import router as admin_router
from app.domains.inventory.router import router as inventory_router
from app.domains.rbac.router import router as rbac_router
from app.domains.coupons.router import router as coupons_router
from app.domains.shipping.router import router as shipping_router
from app.domains.subscriptions.router import router as subscriptions_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(products_router)
api_router.include_router(orders_router)
api_router.include_router(payments_router)
api_router.include_router(push_router)
api_router.include_router(admin_router)
api_router.include_router(cart_router)
api_router.include_router(settings_router)
api_router.include_router(inventory_router)
api_router.include_router(rbac_router)
api_router.include_router(coupons_router)
api_router.include_router(shipping_router)
api_router.include_router(subscriptions_router)
