"""
Payments Domain Policy
======================
Path: app/domains/payments/policy.py

ABAC policy for payment operations.
"""
from app.permissions.policies.payment_policies import PaymentPolicy

__all__ = ["PaymentPolicy"]
