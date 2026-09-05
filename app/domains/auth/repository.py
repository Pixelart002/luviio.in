"""
Auth Domain Repository
======================
Path: app/domains/auth/repository.py

Thin domain-level re-export of the legacy async auth repository. All
Supabase auth calls (sign-up, sign-in, refresh, logout, password reset)
live in the original module.
"""
from app.repositories.auth_repo import AsyncAuthRepository

__all__ = ["AsyncAuthRepository"]
