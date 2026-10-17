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


def test_provider_identity_is_checked_only_when_order_has_identity():
    migration = GUARD.read_text(encoding="utf-8")

    assert "IF nullif(trim(NEW.provider_payment_id), '') IS NOT NULL" in migration
    assert "lower(coalesce(NEW.payment_provider, '')) = 'stripe'" in migration
    assert "The order provider identity must match the successful payment record." in migration


def test_paid_order_guard_does_not_rewrite_historical_orders():
    migration = GUARD.read_text(encoding="utf-8")

    assert "OLD.status IS DISTINCT FROM 'paid'" in migration
    assert "UPDATE public.orders" not in migration


def test_legacy_stripe_rpc_preserves_deployed_signature_and_attempt_flow():
    migration = STRIPE_FIX.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION public.settle_order_transaction(" in migration
    assert "p_ip_address text DEFAULT NULL::text" in migration
    assert "p_user_agent text DEFAULT NULL::text" in migration
    assert "public.record_payment_attempt(" in migration
    assert "public.record_coupon_redemption(" in migration
    assert "PAYMENT_BINDING_MISMATCH" in migration


def test_stripe_settlement_writes_full_value_ledger_before_paid_transition():
    migration = STRIPE_FIX.read_text(encoding="utf-8")

    assert "payment_provider='stripe'" in migration
    assert "provider_payment_id=p_pi_id" in migration
    assert "'stripe',p_pi_id,'payment_received','credit'" in migration
    assert "round(p_amount*100)::bigint" in migration
    assert "ON CONFLICT (provider,provider_payment_id,entry_type)" in migration
    assert "WHERE entry_type <> 'payment_refunded'" in migration
    ledger_write = migration.index("INSERT INTO public.payment_ledger")
    order_paid = migration.index("UPDATE public.orders")
    assert ledger_write < order_paid


def test_stripe_settlement_migration_does_not_backfill_existing_records():
    migration = STRIPE_FIX.read_text(encoding="utf-8")

    assert migration.strip().startswith("BEGIN;")
    assert migration.strip().endswith("COMMIT;")
    # The only order update is the runtime RPC transition, not a historical backfill.
    assert migration.count("UPDATE public.orders") == 1
