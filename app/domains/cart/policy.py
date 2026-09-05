"""
Cart Domain Policy
==================
Path: app/domains/cart/policy.py

ABAC policy for cart operations.
"""
from app.permissions.policies.cart_policies import CartPolicy

__all__ = ["CartPolicy"]
