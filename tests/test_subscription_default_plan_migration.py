from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    REPO_ROOT
    / "migrations/20261017095209_repair_subscription_schema_and_default_free_plan.sql"
)


def test_subscription_schema_drift_is_repaired_idempotently():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS cancelled_at timestamptz" in sql
    assert "ADD COLUMN IF NOT EXISTS cancellation_reason text" in sql
    assert "CREATE TABLE IF NOT EXISTS public.subscription_reminders" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_subscription_reminders_user_status" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_subscription_reminders_due_status" in sql


def test_free_membership_is_provisioned_for_customer_profiles_only():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION public.provision_default_free_subscription()" in sql
    assert "IF NEW.role IS DISTINCT FROM 'customer' THEN" in sql
    assert "AFTER INSERT ON public.users" in sql
    assert "'free', 'active', now()" in sql
    assert "NOT EXISTS (" in sql
    assert "Staff accounts do not receive customer memberships." in sql


def test_backfill_preserves_paid_memberships_and_cancels_staff_free_rows():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "WHERE u.role = 'customer'" in sql
    assert "AND u.role <> 'customer'" in sql
    assert "AND s.tier = 'free'" in sql
    assert "WHERE s.user_id = u.id" in sql
