"""
Auth Domain Policy
==================
Path: app/domains/auth/policy.py

ABAC + brute-force guard for the auth domain. Re-exports the legacy
policy module under the domain namespace.
"""
from app.permissions.policies.auth_policies import AuthPolicy

__all__ = ["AuthPolicy"]
