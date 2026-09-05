"""
RBAC Domain — runtime permission toggles + per-user action controls
===================================================================
Path: app/domains/rbac/__init__.py

Two complementary control planes, both managed by admins at runtime:

  1. Role-level  — enable/disable an individual permission for a whole role
                   (backed by the `role_permissions` override table, layered
                   on top of the static matrix in `app/permissions/base.py`).
  2. User-level  — the "big software" model: disable a specific capability
                   for a SPECIFIC user (backed by `user_action_controls`).
                   e.g. a customer whose subscription payment was never
                   received gets `checkout` / `access_premium_products`
                   blocked until the payment clears.

Enforcement engines (what the rest of the app calls) live in
`app/permissions/` (overrides.py + action_control.py) because they are shared
security infrastructure. THIS package owns the management surface: repository,
service, schemas and the admin router.
"""
from app.domains.rbac.router import router

__all__ = ["router"]
