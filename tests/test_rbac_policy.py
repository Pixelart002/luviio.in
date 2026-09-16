import pytest
from fastapi import HTTPException

from app.enums.roles import UserRole
from app.permissions.policies.user_policies import UserPolicy


def test_super_admin_can_manage_any_role():
    UserPolicy.assert_role_change_allowed(
        UserRole.SUPER_ADMIN,
        UserRole.SUPER_ADMIN,
        UserRole.ADMIN,
    )


def test_admin_can_assign_lower_staff_roles():
    for role in (UserRole.MANAGER, UserRole.SUPPORT, UserRole.CUSTOMER):
        UserPolicy.assert_role_change_allowed(UserRole.ADMIN, UserRole.CUSTOMER, role)


def test_admin_cannot_promote_to_super_admin():
    with pytest.raises(HTTPException) as exc:
        UserPolicy.assert_role_change_allowed(
            UserRole.ADMIN,
            UserRole.CUSTOMER,
            UserRole.SUPER_ADMIN,
        )
    assert exc.value.status_code == 403


def test_admin_cannot_modify_an_admin_role():
    with pytest.raises(HTTPException) as exc:
        UserPolicy.assert_role_change_allowed(
            UserRole.ADMIN,
            UserRole.ADMIN,
            UserRole.MANAGER,
        )
    assert exc.value.status_code == 403


def test_admin_cannot_change_super_admin_role():
    with pytest.raises(HTTPException) as exc:
        UserPolicy.assert_role_change_allowed(
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN,
            UserRole.ADMIN,
        )
    assert exc.value.status_code == 403
