from pathlib import Path


def test_paid_order_guard_requires_successful_payment_and_matching_ledger_credit():
    migration = Path(
        "migrations/20261017121500_guard_paid_order_settlement_evidence.sql"
    ).read_text(encoding="utf-8")

    assert "BEFORE UPDATE OF status ON public.orders" in migration
    assert "NEW.status = 'paid' AND OLD.status IS DISTINCT FROM 'paid'" in migration
    assert "lower(coalesce(p.status, '')) = 'succeeded'" in migration
    assert "l.entry_type = 'payment_received'" in migration
    assert "l.direction = 'credit'" in migration
    assert "l.amount_paise = v_amount_paise" in migration
    assert "ORDER_PAID_REQUIRES_SETTLED_PAYMENT" in migration
    assert "ORDER_PAID_PROVIDER_IDENTITY_MISMATCH" in migration


def test_paid_order_guard_does_not_rewrite_historical_orders():
    migration = Path(
        "migrations/20261017121500_guard_paid_order_settlement_evidence.sql"
    ).read_text(encoding="utf-8")

    # Guard is transition-based: it runs only when a row changes into paid.
    assert "OLD.status IS DISTINCT FROM 'paid'" in migration
    assert "UPDATE public.orders" not in migration
