"""
Products Domain Policy
======================
Path: app/domains/products/policy.py

ABAC policy for product catalog operations.
"""
from app.permissions.policies.product_policies import ProductPolicy

__all__ = ["ProductPolicy"]
