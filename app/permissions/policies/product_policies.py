"""
Product Attribute-Based Access Control (ABAC) Policies
======================================================
Path: app/permissions/policies/product_policies.py

Architecture & Features:
  ✅ Unified Policy Engine — Merges catalog domain guards with RBAC inventory modification rules.
  ✅ Data Integrity Guards — Enforces strict validation on image indexing, ordering, and upload limits.
  ✅ Taxonomy Protection — Blocks deletion of non-empty categories to preserve referential integrity.
  ✅ Role Hierarchy Support — Enforces Manager+ privileges for physical inventory (stock) mutations.
"""
import logging
from typing import List, Optional
from fastapi import HTTPException, status

from app.enums.roles import UserRole
from app.constants.product_messages import ProductSecurityMessages, ProductRules
from app.core.exceptions import UnauthorizedAction

logger = logging.getLogger(__name__)


class ProductPolicy:
    """Enforces catalog integrity, storage limits, taxonomy rules, and inventory RBAC hierarchies."""

    # ══════════════════════════════════════════════════════════════════════════
    #  ASSERTION GUARDS (FastAPI Route & Service Protectors)
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def assert_can_modify_inventory(user_role: Optional[str]) -> None:
        """
        ABAC Guard: Verifies that the user holds sufficient privileges (Manager+)
        to mutate physical inventory stock levels.
        """
        if not user_role:
            logger.warning("ABAC Block | Inventory modification attempted without role.")
            raise UnauthorizedAction("Inventory modification requires Manager privileges or higher.")

        privileged_roles = {
            UserRole.SUPER_ADMIN.value if hasattr(UserRole.SUPER_ADMIN, "value") else "super_admin",
            UserRole.ADMIN.value if hasattr(UserRole.ADMIN, "value") else "admin",
            UserRole.MANAGER.value if hasattr(UserRole.MANAGER, "value") else "manager",
        }

        if str(user_role).lower() not in privileged_roles:
            logger.warning("ABAC Block | User with role '%s' attempted to modify inventory.", user_role)
            raise UnauthorizedAction("Inventory modification requires Manager privileges or higher.")

    @staticmethod
    def assert_can_delete_category(active_product_count: int) -> None:
        """
        ABAC Guard: Prevents deletion of categories that currently house active products.
        """
        if active_product_count > 0:
            logger.warning("ABAC Block | Attempted to delete category containing %d active products.", active_product_count)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ProductSecurityMessages.CATEGORY_NOT_EMPTY
            )

    @staticmethod
    def assert_can_upload_image(current_image_count: int) -> None:
        """
        ABAC Guard: Enforces cloud storage limits per product to prevent resource abuse.
        """
        if current_image_count >= ProductRules.MAX_IMAGES_PER_PRODUCT:
            logger.warning("ABAC Block | Product exceeded max image limit of %d.", ProductRules.MAX_IMAGES_PER_PRODUCT)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ProductSecurityMessages.MAX_IMAGES_EXCEEDED.format(limit=ProductRules.MAX_IMAGES_PER_PRODUCT)
            )

    @staticmethod
    def assert_valid_image_index(index: int, total_images: int) -> None:
        """
        ABAC Guard: Validates array bounds prior to image removal operations.
        """
        if index < 0 or index >= total_images:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ProductSecurityMessages.INVALID_IMAGE_INDEX
            )

    @staticmethod
    def assert_valid_image_reorder(existing_urls: List[str], requested_urls: List[str]) -> None:
        """
        ABAC Guard: Ensures admins are only reordering existing images, not injecting foreign URLs.
        """
        if set(existing_urls) != set(requested_urls) or len(existing_urls) != len(requested_urls):
            logger.warning("ABAC Block | Invalid image URLs provided during reordering.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ProductSecurityMessages.INVALID_IMAGE_REORDER
            )

    # ══════════════════════════════════════════════════════════════════════════
    #  BOOLEAN EVALUATORS (Legacy & Fine-Grained Check Support)
    # ══════════════════════════════════════════════════════════════════════════

    @classmethod
    def can_modify_inventory(cls, user_role: str) -> bool:
        """
        Policy Evaluator: Checks if a role can modify inventory without raising an HTTPException.
        Useful for background workers, non-HTTP domain services, or conditional UI logic.
        """
        cls.assert_can_modify_inventory(user_role)
        return True
