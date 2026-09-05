"""
Admin Domain
============
Path: app/domains/admin/__init__.py

Owns admin verification, dashboard stats, and admin-privileged actions.
"""
from app.domains.admin.service import AdminService
from app.domains.admin.policy import AdminPolicy
from app.domains.admin.repository import AsyncAdminRepository

__all__ = ["AdminService", "AdminPolicy", "AsyncAdminRepository"]
