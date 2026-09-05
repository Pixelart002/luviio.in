"""
Users Domain Policy
===================
Path: app/domains/users/policy.py

ABAC policy for profile, address, and admin self-modification guards.
"""
from app.permissions.policies.user_policies import UserPolicy

__all__ = ["UserPolicy"]
