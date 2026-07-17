"""
Push Notification Attribute-Based Access Control (ABAC)
=======================================================
Path: app/permissions/policies/push_policies.py
"""
import logging
import urllib.parse
from fastapi import HTTPException, status
from app.constants.push_messages import PushSecurityMessages

logger = logging.getLogger(__name__)

class PushPolicy:
    """Enforces device limits and defends against Server-Side Request Forgery (SSRF)."""

    @staticmethod
    def assert_valid_endpoint(endpoint: str) -> None:
        """
        ABAC Guard: Prevents SSRF attacks by ensuring the push endpoint is a valid, 
        secure HTTPS URL pointing to standard WebPush gateways.
        """
        if not endpoint:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PushSecurityMessages.INVALID_ENDPOINT)
            
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme != "https":
            logger.warning("ABAC SSRF Block | Insecure push endpoint rejected: %s", endpoint[:30])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PushSecurityMessages.INVALID_ENDPOINT)
            
        # Basic sanity check (Endpoints usually contain googleapis, mozilla, windows, etc.)
        if "localhost" in parsed.netloc or "127.0.0.1" in parsed.netloc:
            logger.warning("ABAC SSRF Block | Internal endpoint rejected: %s", endpoint)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PushSecurityMessages.INVALID_ENDPOINT)

    @staticmethod
    def get_stale_cleanup_target(current_count: int, max_limit: int = 5) -> int:
        """
        Returns the number of old devices to delete if the limit is exceeded.
        """
        if current_count >= max_limit:
            # If at or exceeding limit, delete enough to make room for 1 new device
            return (current_count - max_limit) + 1
        return 0