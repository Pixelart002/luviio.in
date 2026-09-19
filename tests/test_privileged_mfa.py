from unittest.mock import AsyncMock, patch

import pytest

from app.core.dependencies import require_permission
from app.core.exceptions import UnauthorizedAction


@pytest.mark.asyncio
async def test_privileged_permission_requires_aal2():
    checker = require_permission("admin.access_console")
    current = {
        "sub": "staff-1",
        "aal": "aal1",
        "profile": {"role": "admin"},
    }
    with patch(
        "app.core.dependencies.get_effective_permissions",
        new=AsyncMock(return_value={"admin.access_console"}),
    ):
        with pytest.raises(UnauthorizedAction, match="MFA verification required") as exc_info:
            await checker(current)
    assert exc_info.value.code == "MFA_REQUIRED"


@pytest.mark.asyncio
async def test_privileged_permission_allows_aal2():
    checker = require_permission("admin.access_console")
    current = {
        "sub": "staff-1",
        "aal": "aal2",
        "profile": {"role": "admin"},
    }
    with patch(
        "app.core.dependencies.get_effective_permissions",
        new=AsyncMock(return_value={"admin.access_console"}),
    ):
        result = await checker(current)
    assert result is current


@pytest.mark.asyncio
async def test_customer_permission_does_not_require_mfa():
    checker = require_permission("coupons.apply")
    current = {
        "sub": "customer-1",
        "aal": "aal1",
        "profile": {"role": "customer"},
    }
    with patch(
        "app.core.dependencies.get_effective_permissions",
        new=AsyncMock(return_value={"coupons.apply"}),
    ):
        result = await checker(current)
    assert result is current
