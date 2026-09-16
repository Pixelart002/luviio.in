from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _invoice_immutability_migration() -> str:
    matches = sorted(MIGRATIONS.glob("*invoice*snapshot*immut*.sql"))
    if not matches:
        matches = sorted(MIGRATIONS.glob("*invoice*snapshot*.sql"))
    assert matches, "invoice snapshot immutability migration is missing"
    return matches[-1].read_text(encoding="utf-8").lower()


def test_invoice_snapshot_mutation_trigger_is_present():
    source = _invoice_immutability_migration()
    assert "trg_prevent_invoice_snapshot_mutation" in source
    assert "before delete or update on public.invoices" in source
    assert "prevent_invoice_snapshot_mutation" in source


def test_invoice_snapshot_immutable_identity_and_financial_fields_are_guarded():
    source = _invoice_immutability_migration()
    for field in (
        "order_id",
        "invoice_number",
        "issued_at",
        "currency",
        "tax_type",
        "seller_snapshot",
        "billing_snapshot",
        "shipping_snapshot",
        "totals_snapshot",
    ):
        assert f"new.{field} is distinct from old.{field}" in source
    assert "raise exception 'invoice_snapshot_immutable'" in source


def test_invoice_item_snapshot_is_immutable():
    source = _invoice_immutability_migration()
    assert "trg_prevent_invoice_item_mutation" in source
    assert "before delete or update on public.invoice_items" in source
    assert "invoice_item_snapshot_immutable" in source
