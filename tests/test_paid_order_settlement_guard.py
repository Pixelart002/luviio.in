from pathlib import Path

GUARD = Path(
    "migrations/20261017121500_guard_paid_order_settlement_evidence.sql"
)
STRIPE_FIX = Path(
    "migrations/20261017123000_stripe_settlement_writes_ledger.sql"
)


def test_paid_order_guard_requires_successful_payment_and_matching_ledger_credit():
    migration = GUARD.read_text(encoding="utf-8")

    assert "BEFORE UPDATE OF status ON public.orders" in migration
    assert "NEW.status = 'paid' AND OLD.status IS DISTINCT FROM 'paid'" in migration
    assert "lower(coalesce(p.status, '')) = 'succeeded'" in migration
    assert "l.entry_type = 'payment_received'" in migration
    assert "l.direction = 'credit'" in migration
    assert "l.amount_paise = v_amount_paise" in migration
    assert "ORDER_PAID_REQUIRES_SETTLED_PAYMENT" in migration
    assert "ORDER_PAID_PROVIDER_IDENTITY_MISMATCH" in migration


def test_paid_order_guard_does_not_rewrite_historical_orders():
    migration = GUARD.read_text(encoding="utf-8")

    # Guard is transition-based: it runs only when a row changes into paid.
    assert "OLD.status IS DISTINCT FROM 'paid'" in migration
    assert "UPDATE public.orders" not in migration


def test_legacy_stripe_settlement_writes_matching_ledger_before_paid_transition():
    migration = STRIPE_FIX.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION public.settle_order_transaction(" in migration
    assert "payment_provider='stripe'" in migration
    assert "provider_payment_id=EXCLUDED.provider_payment_id" in migration
    assert "'stripe',p_pi_id,'payment_received','credit'" in migration
    assert "ON CONFLICT(provider,provider_payment_id,entry_type) DO NOTHING" in migration
    ledger_write = migration.index("INSERT INTO public.payment_ledger")
    order_paid = migration.index("UPDATE public.orders")
    assert ledger_write < order_paid
    assert "public.record_coupon_redemption" in migration
    assert "payment_retry_reservations" in migration


def test_stripe_settlement_is_atomic_and_does_not_touch_historical_orders():
    migration = STRIPE_FIX.read_text(encoding="utf-8")

    assert migration.strip().startswith("BEGIN;")
    assert migration.strip().endswith("COMMIT;")
    # This migration replaces the settlement routine only; no backfill/update
    # is run against existing order or payment rows.
    assert "UPDATE public.orders" in migration
    assert "WHERE id=p_order_id;" in migration
    assert "UPDATE public.payment_ledger" not in migration
