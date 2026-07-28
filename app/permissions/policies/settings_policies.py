"""
Settings ABAC Policies
======================
Path: app/permissions/policies/settings_policies.py
"""
import logging
from typing import Any, Dict, Optional
from fastapi import HTTPException, status
from app.constants.settings_messages import SettingsSecurityMessages
from app.enums.roles import UserRole
from app.enums.settings import SettingDataType

logger = logging.getLogger(__name__)

class SettingsPolicy:
    @staticmethod
    def assert_can_modify(setting: Optional[Dict[str, Any]], user_role: str) -> Dict[str, Any]:
        """ABAC Guard: Verifies setting existence and prevents lower-tier admins from touching locked configs."""
        if not setting:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SettingsSecurityMessages.NOT_FOUND
            )

        is_locked = setting.get("is_system_locked", False)
        super_admin_role = UserRole.SUPER_ADMIN.value if hasattr(UserRole.SUPER_ADMIN, "value") else "super_admin"

        if is_locked and str(user_role).lower() != super_admin_role:
            logger.warning("ABAC Block | Role '%s' attempted to modify system-locked key: %s", user_role, setting.get("key"))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=SettingsSecurityMessages.LOCKED_SETTING
            )

        return setting

    @staticmethod
    def assert_valid_data_type(value: Any, expected_type: str) -> None:
        """ABAC Guard: Enforces strict data type compliance before DB persistence."""
        try:
            if expected_type == SettingDataType.BOOLEAN and not isinstance(value, bool):
                raise ValueError()
            elif expected_type == SettingDataType.INTEGER and not isinstance(value, int):
                raise ValueError()
            elif expected_type == SettingDataType.DECIMAL and not isinstance(value, (int, float)):
                raise ValueError()
            elif expected_type == SettingDataType.STRING and not isinstance(value, str):
                raise ValueError()
            elif expected_type == SettingDataType.JSON and not isinstance(value, (dict, list)):
                raise ValueError()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=SettingsSecurityMessages.TYPE_MISMATCH.format(expected_type=expected_type)
            )