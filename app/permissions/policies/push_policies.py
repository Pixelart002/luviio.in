"""
Push Notification Policy Guards
===============================
Path: app/permissions/policies/push_policies.py
"""
import os
import logging
from fastapi import HTTPException, status
from app.constants.push_messages import PushSecurityMessages

logger = logging.getLogger(__name__)

# Fetch key at startup safely
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")

class PushPolicy:
    @staticmethod
    def assert_vapid_configured() -> str:
        """ABAC Guard: Prevents system crashes if Push config is missing in ENV."""
        if not VAPID_PUBLIC_KEY:
            logger.error("VAPID key is missing in environment variables.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
                detail=PushSecurityMessages.NOT_CONFIGURED
            )
        return VAPID_PUBLIC_KEY

    @staticmethod
    def assert_valid_endpoint(endpoint: str) -> None:
        """ABAC Guard: Enforces HTTPS for WebPush endpoints to prevent Man-in-the-Middle attacks."""
        if not endpoint or not endpoint.startswith("https://"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=PushSecurityMessages.INVALID_ENDPOINT
            )