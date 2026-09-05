"""
Master API Router — Enterprise Grade
====================================
Path: app/api/v1/api.py

Combines all v1 routers into a single master router.

Routers are imported from their canonical DOMAIN homes under
`app/domains/<name>/router.py`. Each domain module re-exports the same
router object, so the resulting route table is unchanged.
"""
from fastapi import APIRouter

# ── Infrastructure routers (not domain-scoped) ────────────────────────────────
from app.api.v1.routers import health, invoice

# ── Domain routers ────────────────────────────────────────────────────────────
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

# ── SYSTEM ROUTES ─────────────────────────────────────────────────────────────
api_router.include_router(health.router)

# ── DOMAIN ROUTES ─────────────────────────────────────────────────────────────
api_router.include_router(auth_router)          # /auth
api_router.include_router(users_router)         # /users
api_router.include_router(products_router)      # /products
api_router.include_router(orders_router)        # /orders
api_router.include_router(payments_router)      # /payments
api_router.include_router(push_router)          # /push
api_router.include_router(admin_router)         # /admin (verify + dashboard)
api_router.include_router(cart_router)          # /cart
api_router.include_router(invoice.router)       # /invoice
api_router.include_router(settings_router)      # /settings
api_router.include_router(inventory_router)     # /inventory — stock, reservations, low-stock alerts
api_router.include_router(rbac_router)          # /rbac — role overrides + per-user action control
api_router.include_router(coupons_router)       # /coupons — promo codes + redemption
api_router.include_router(shipping_router)      # /shipping — methods + rate calc
api_router.include_router(subscriptions_router) # /subscriptions — tiers, plans, membership
