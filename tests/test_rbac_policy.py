import pytest
from fastapi import HTTPException

from app.domains.rbac.policy import RbacPolicy
from app.enums.roles import UserRole
from app.permissions.base import get_static_role_permissions
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


def test_self_demotion_is_blocked():
    with pytest.raises(HTTPException) as exc:
        UserPolicy.assert_admin_not_downgrading_self(
            "admin-1",
            "admin-1",
            {"role": UserRole.MANAGER.value},
        )
    assert exc.value.status_code == 403


def test_self_deactivation_is_blocked():
    with pytest.raises(HTTPException) as exc:
        UserPolicy.assert_admin_not_downgrading_self(
            "admin-1",
            "admin-1",
            {"is_active": False},
        )
    assert exc.value.status_code == 403


def test_self_update_without_demotion_is_allowed():
    UserPolicy.assert_admin_not_downgrading_self(
        "admin-1",
        "admin-1",
        {"role": UserRole.ADMIN.value, "is_active": True},
    )


def test_super_admin_can_manage_any_rbac_override_role():
    for role in UserRole:
        RbacPolicy.assert_role_manageable(UserRole.SUPER_ADMIN.value, role.value)


def test_admin_can_manage_only_lower_rbac_override_roles():
    for role in (UserRole.MANAGER, UserRole.SUPPORT, UserRole.CUSTOMER):
        RbacPolicy.assert_role_manageable(UserRole.ADMIN.value, role.value)


def test_admin_cannot_modify_admin_rbac_permissions():
    with pytest.raises(HTTPException) as exc:
        RbacPolicy.assert_role_manageable(UserRole.ADMIN.value, UserRole.ADMIN.value)
    assert exc.value.status_code == 403


def test_admin_cannot_modify_super_admin_rbac_permissions():
    with pytest.raises(HTTPException) as exc:
        RbacPolicy.assert_role_manageable(
            UserRole.ADMIN.value,
            UserRole.SUPER_ADMIN.value,
        )
    assert exc.value.status_code == 403


def test_lower_staff_roles_cannot_modify_rbac_overrides():
    for actor in (UserRole.MANAGER, UserRole.SUPPORT, UserRole.CUSTOMER):
        with pytest.raises(HTTPException) as exc:
            RbacPolicy.assert_role_manageable(actor.value, UserRole.CUSTOMER.value)
        assert exc.value.status_code == 403


def test_self_action_disable_is_blocked():
    with pytest.raises(HTTPException) as exc:
        RbacPolicy.assert_not_self_lockout("admin-1", "admin-1", "checkout", False)
    assert exc.value.status_code == 400


def test_self_action_override_removal_is_blocked():
    with pytest.raises(HTTPException) as exc:
        RbacPolicy.assert_not_self_lockout("admin-1", "admin-1", "checkout", False)
    assert exc.value.status_code == 400


def test_other_user_action_control_can_be_changed():
    RbacPolicy.assert_not_self_lockout("admin-1", "user-2", "checkout", False)


def test_inventory_permissions_are_present_for_expected_roles():
    admin = get_static_role_permissions(UserRole.ADMIN)
    manager = get_static_role_permissions(UserRole.MANAGER)
    support = get_static_role_permissions(UserRole.SUPPORT)

    inventory_mutations = {
        "inventory.adjust",
        "inventory.receive",
        "inventory.return",
        "inventory.damage",
        "inventory.wastage",
        "inventory.reconcile",
        "inventory.reservation.release",
        "inventory.low_stock.scan",
    }
    inventory_reads = {
        "inventory.read",
        "inventory.history.read",
        "inventory.low_stock.read",
    }

    assert inventory_mutations.issubset(admin)
    assert inventory_mutations.issubset(manager)
    assert inventory_reads.issubset(admin)
    assert inventory_reads.issubset(manager)
    assert inventory_reads.issubset(support)
    assert inventory_mutations.isdisjoint(support)


def test_abandoned_cart_permissions_are_present_for_admin_and_manager():
    admin = get_static_role_permissions(UserRole.ADMIN)
    manager = get_static_role_permissions(UserRole.MANAGER)
    support = get_static_role_permissions(UserRole.SUPPORT)

    cart_admin_permissions = {
        "cart:view_abandoned",
        "cart:manage_reminders",
    }

    assert cart_admin_permissions.issubset(admin)
    assert cart_admin_permissions.issubset(manager)
    assert cart_admin_permissions.isdisjoint(support)
