"""
Admin Domain Policy
===================
Path: app/domains/admin/policy.py

ABAC policy for admin-only operations.
"""
from app.permissions.policies.admin_policies import AdminPolicy

__all__ = ["AdminPolicy"]
