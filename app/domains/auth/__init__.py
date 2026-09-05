"""
Auth Domain
===========
Path: app/domains/auth/__init__.py

Public entry point for the auth domain. The domain owns:
- Identity lifecycle (register / login / refresh / logout)
- Password recovery (forgot / reset)
- Brute-force / credential-stuffing policy

Canonical home for: AuthService, AuthPolicy, AsyncAuthRepository,
auth DTOs and the /api/v1/auth router.
"""
from app.domains.auth.service import AuthService
from app.domains.auth.policy import AuthPolicy
from app.domains.auth.repository import AsyncAuthRepository

__all__ = ["AuthService", "AuthPolicy", "AsyncAuthRepository"]
