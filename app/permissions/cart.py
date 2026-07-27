"""
Cart RBAC Permissions (SSOT)
============================
Path: app/permissions/cart.py

Defines explicit administrative permissions required for cart analytics
and abandoned cart recovery workflows.
"""

class CartPermissions:
    VIEW_ABANDONED = "cart:view_abandoned"
    MANAGE_REMINDERS = "cart:manage_reminders"