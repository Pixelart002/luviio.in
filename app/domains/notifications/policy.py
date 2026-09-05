"""
Notifications Domain Policy
===========================
Path: app/domains/notifications/policy.py

ABAC policy for push notification operations.
"""
from app.permissions.policies.push_policies import PushPolicy

__all__ = ["PushPolicy"]
