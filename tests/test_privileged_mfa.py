from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.dependencies import require_permission
from app.core.exceptions import MFARequired, UnauthorizedAction
from app.domains.auth.mfa import _provider_error_message


def test_mfa_provider_error_prefers_message_fields():
    response = SimpleNamespace(status_code=400, text='{"error":"invalid"}')
    data = {"msg": "TOTP is not enabled for this project."}
    assert _provider_error_message(response, data) == "TOTP is not enabled for this project."


def test_mfa_provider_error_falls_back_to_http_status_and_body():
    response = SimpleNamespace(status_code=404, text="not found")
    assert _provider_error_message(response, {}) == "Supabase Auth MFA request failed (HTTP 404): not found"


@pytest.mark.asyncio
async def test_privileged_permission_requires_aal2():
    checker = require_permission("admin.access_console")
    current = {"sub": "staff-1", "aal": "aal1", "profile": {"role": "admin"}}
    with patch("app.core.dependencies.get_effective_permissions", new=AsyncMock(return_value={"admin.access_console"})):
        with pytest.raises(MFARequired, match="MFA verification required") as exc_info:
            await checker(current)
    assert exc_info.value.code == "MFA_REQUIRED"


@pytest.mark.asyncio
async def test_privileged_permission_allows_aal2():
    checker = require_permission("admin.access_console")
    current = {"sub": "staff-1", "aal": "aal2", "profile": {"role": "admin"}}
    with patch("app.core.dependencies.get_effective_permissions", new=AsyncMock(return_value={"admin.access_console"})):
        result = await checker(current)
    assert result is current


@pytest.mark.asyncio
async def test_customer_permission_does_not_require_mfa():
    checker = require_permission("coupons.apply")
    current = {"sub": "customer-1", "aal": "aal1", "profile": {"role": "customer"}}
    with patch("app.core.dependencies.get_effective_permissions", new=AsyncMock(return_value={"coupons.apply"})):
        result = await checker(current)
    assert result is current
