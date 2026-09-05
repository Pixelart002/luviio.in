"""
Auth Domain Service
===================
Path: app/domains/auth/service.py

Re-exports the canonical AuthService from the legacy services location.
The service orchestrates register / login / refresh / logout / password
recovery and delegates credential-abuse prevention to AuthPolicy.
"""
from app.services.auth.service import AuthService

__all__ = ["AuthService"]
