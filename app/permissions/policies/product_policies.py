"""
Product Attribute-Based Access Control (ABAC) Policies
======================================================
Path: app/permissions/policies/product_policies.py
"""
import logging
from typing import List
from fastapi import HTTPException, status
from app.constants.product_messages import ProductSecurityMessages, ProductRules

logger = logging.getLogger(__name__)

class ProductPolicy:
    """Enforces catalog integrity, storage limits, and state machine rules."""

    @staticmethod
    def assert_can_delete_category(active_product_count: int) -> None:
        """ABAC Guard: Prevents deletion of categories that have active products."""
        if active_product_count > 0:
            logger.warning(f"ABAC Block | Attempted to delete category containing {active_product_count} active products.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ProductSecurityMessages.CATEGORY_NOT_EMPTY
            )

    @staticmethod
    def assert_can_upload_image(current_image_count: int) -> None:
        """ABAC Guard: Enforces cloud storage limits per product to prevent abuse."""
        if current_image_count >= ProductRules.MAX_IMAGES_PER_PRODUCT:
            logger.warning(f"ABAC Block | Product exceeded max image limit of {ProductRules.MAX_IMAGES_PER_PRODUCT}.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ProductSecurityMessages.MAX_IMAGES_EXCEEDED.format(limit=ProductRules.MAX_IMAGES_PER_PRODUCT)
            )

    @staticmethod
    def assert_valid_image_index(index: int, total_images: int) -> None:
        """ABAC Guard: Validates array bounds for image deletion."""
        if index < 0 or index >= total_images:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ProductSecurityMessages.INVALID_IMAGE_INDEX
            )

    @staticmethod
    def assert_valid_image_reorder(existing_urls: List[str], requested_urls: List[str]) -> None:
        """ABAC Guard: Ensures admins are only reordering existing images, not injecting foreign URLs."""
        if set(existing_urls) != set(requested_urls):
            logger.warning("ABAC Block | Invalid image URLs provided during reordering.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ProductSecurityMessages.INVALID_IMAGE_REORDER
            )