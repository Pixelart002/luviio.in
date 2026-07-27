"""
Push Notification Policy Guards
===============================
Path: app/permissions/policies/push_policies.py
"""
import os
import logging
from typing import List
from fastapi import HTTPException, status
from app.constants.push_messages import PushSecurityMessages, PushRules

logger = logging.getLogger(__name__)

# Fetch key at startup safely
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")

class PushPolicy:
    @staticmethod
    def assert_vapid_configured() -> str:
        """ABAC Guard: Prevents system crashes if Push config is missing in ENV."""
        if not VAPID_PUBLIC_KEY:
            logger.error("Security Alert | VAPID public key is missing in server environment.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
                detail=PushSecurityMessages.NOT_CONFIGURED
            )
        return VAPID_PUBLIC_KEY

    @staticmethod
    def assert_valid_endpoint(endpoint: str) -> None:
        """ABAC Guard: Enforces HTTPS for WebPush endpoints to prevent MitM payload interception."""
        if not endpoint or not endpoint.startswith("https://"):
            logger.warning("Security Block | Insecure HTTP push endpoint rejected: %s", endpoint[:50])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=PushSecurityMessages.INVALID_ENDPOINT
            )

    @staticmethod
    def assert_valid_batch_size(user_ids: List[str]) -> None:
        """ABAC Guard: Enforces hard ceilings on broadcast sizes to protect relay servers."""
        if len(user_ids) > PushRules.MAX_BATCH_SIZE:
            logger.warning("ABAC Block | Batch notification exceeded limit: %d users.", len(user_ids))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=PushSecurityMessages.BATCH_LIMIT_EXCEEDED.format(limit=PushRules.MAX_BATCH_SIZE)
            )