from pathlib import Path

import pytest
from fastapi import HTTPException

from app.domains.orders.service import STATUS_TRANSITIONS
from app.enums.order_status import OrderStatus
from app.permissions.policies.order_policies import OrderPolicy

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_paid_and_processing_orders_cannot_directly_cancel():
    assert OrderStatus.CANCELLED not in STATUS_TRANSITIONS[OrderStatus.PAID]
    assert OrderStatus.CANCELLED not in STATUS_TRANSITIONS[OrderStatus.PROCESSING]


def test_pending_orders_remain_directly_cancellable():
    assert OrderStatus.CANCELLED in STATUS_TRANSITIONS[OrderStatus.PENDING]
    OrderPolicy.assert_can_cancel(
        {"customer_id": "user-1", "status": OrderStatus.PENDING.value},
        "user-1",
    )


@pytest.mark.parametrize("status_value", [OrderStatus.PAID.value, OrderStatus.PROCESSING.value])
def test_paid_or_processing_policy_requires_refund_workflow(status_value):
    with pytest.raises(HTTPException) as exc:
        OrderPolicy.assert_can_cancel(
            {"customer_id": "user-1", "status": status_value},
            "user-1",
        )
    assert exc.value.status_code == 409


def test_orders_repository_no_longer_owns_stock_cancellation():
    source = (REPO_ROOT / "app/domains/orders/repository.py").read_text(encoding="utf-8")
    assert "cancel_order_and_restore_stock" not in source


def test_refunded_orders_cannot_download_invoice():
    with pytest.raises(HTTPException) as exc:
        OrderPolicy.assert_can_download_invoice(
            {"customer_id": "user-1", "status": OrderStatus.REFUNDED.value},
            "user-1",
        )
    assert exc.value.status_code == 409


def test_processing_orders_can_download_invoice():
    OrderPolicy.assert_can_download_invoice(
        {"customer_id": "user-1", "status": OrderStatus.PROCESSING.value},
        "user-1",
    )


def test_order_service_routes_cancellation_to_inventory_domain():
    source = (REPO_ROOT / "app/domains/orders/service.py").read_text(encoding="utf-8")
    assert "InventoryService" in source
    assert "self.inventory.cancel_order_with_stock_restoration" in source

def test_legacy_cancel_overload_does_not_restore_cart():
    migration = (REPO_ROOT / "migrations/20260918033000_remove_legacy_cancel_cart_restore.sql").read_text(encoding="utf-8")
    assert "INSERT INTO public.carts" not in migration
    assert "INSERT INTO public.cart_items" not in migration
    assert "p_target_status" not in migration
    assert "public.cancel_order_and_release_stock(p_order_id, p_reason, 'cancelled'::text)" in migration
