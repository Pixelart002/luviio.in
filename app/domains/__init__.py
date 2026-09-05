"""
Luviio Domains
==============
Path: app/domains/__init__.py

Domain-Driven Design boundary layer. Each subpackage owns its full vertical
slice — schemas, policy, repository, service, and router — and re-exports the
canonical implementation so the rest of the application can import from a
single stable home.

Domains
-------
- auth          : identity lifecycle, password recovery, brute-force policy
- users         : profiles, address book, admin user operations
- products      : catalog CRUD, images, public listing & search
- inventory     : stock levels, reservations, low-stock alerts, stale sweeps
- cart          : line items, cart totals, abandoned-cart recovery
- pricing       : standard / zero-tax / free-shipping strategy selection
- orders        : order lifecycle, FSM transitions, cancellation, invoices
- payments      : payment intents, confirmation, Stripe webhooks, settlement
- notifications : push subscriptions, delivery, batch campaigns
- settings      : dynamic system settings + role-scoped views
- admin         : admin verification and dashboard statistics
- rbac          : role/permission overrides + per-user action control
- coupons       : promo codes, redemption, checkout discount resolution
- shipping      : shipping methods + rate computation
- subscriptions : tier registry (free/premium/platinum), plans, membership

Refactor order honoured (per spec): Inventory -> Cart -> Pricing -> Orders ->
Payments -> Shipping -> Notifications -> supporting domains.

Shipping note: shipping cost + free-shipping threshold have historically been
computed by the pricing domain (``FreeShippingPricing``) and persisted onto
orders. The standalone ``shipping`` domain now provides real shipping-method
CRUD + rate computation as a richer, admin-manageable layer, while pricing
still supplies the zero-regression default during checkout.
"""

DOMAINS = (
    "auth",
    "users",
    "products",
    "inventory",
    "cart",
    "pricing",
    "orders",
    "payments",
    "notifications",
    "settings",
    "admin",
    "rbac",
    "coupons",
    "shipping",
    "subscriptions",
)

__all__ = list(DOMAINS)
