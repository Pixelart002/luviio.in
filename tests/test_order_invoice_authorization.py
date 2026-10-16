from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import MFARequired, UnauthorizedAction
from app.domains.orders.router import _invoice_admin_access
from app.permissions.orders import OrderPermissions


@pytest.mark.asyncio
async def test_staff_invoice_access_requires_aal2(monkeypatch):
    monkeypatch.setattr(
        "app.core.dependencies.get_effective_permissions",
        AsyncMock(return_value={OrderPermissions.READ}),
    )

    with pytest.raises(MFARequired):
        await _invoice_admin_access({"aal": "aal1", "profile": {"role": "admin"}})


@pytest.mark.asyncio
async def test_staff_invoice_access_requires_order_read_permission(monkeypatch):
    monkeypatch.setattr(
        "app.core.dependencies.get_effective_permissions",
        AsyncMock(return_value=set()),
    )

    with pytest.raises(UnauthorizedAction):
        await _invoice_admin_access({"aal": "aal2", "profile": {"role": "manager"}})


@pytest.mark.asyncio
async def test_staff_invoice_access_allows_aal2_with_order_read(monkeypatch):
    monkeypatch.setattr(
        "app.core.dependencies.get_effective_permissions",
        AsyncMock(return_value={OrderPermissions.READ}),
    )

    assert await _invoice_admin_access(
        {"aal": "aal2", "profile": {"role": "admin"}}
    ) is True


@pytest.mark.asyncio
async def test_customer_invoice_access_does_not_grant_cross_customer_bypass(monkeypatch):
    permissions = AsyncMock(return_value=set())
    monkeypatch.setattr("app.core.dependencies.get_effective_permissions", permissions)

    assert await _invoice_admin_access(
        {"aal": "aal1", "profile": {"role": "customer"}}
    ) is False
    permissions.assert_not_awaited()
