"""
Admin Domain
============
Path: app/domains/admin/__init__.py

Owns admin verification, dashboard stats, and admin-privileged actions.
"""
from app.domains.admin.policy import AdminPolicy
from app.domains.admin.repository import AsyncAdminRepository
from app.domains.admin.service import AdminService

__all__ = ["AdminService", "AdminPolicy", "AsyncAdminRepository"]
