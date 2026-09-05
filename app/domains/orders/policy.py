"""
Orders Domain Policy
====================
Path: app/domains/orders/policy.py

ABAC policy for order viewing, cancellation, and invoice access.
"""
from app.permissions.policies.order_policies import OrderPolicy

__all__ = ["OrderPolicy"]
