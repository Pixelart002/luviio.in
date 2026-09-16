from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _invoice_snapshot_migration() -> str:
    path = MIGRATIONS / "20260916210000_snapshot_compare_price_for_invoice_display.sql"
    assert path.exists(), "invoice snapshot migration is missing"
    return path.read_text(encoding="utf-8").lower()


def test_invoice_snapshot_insert_contains_immutable_order_fields():
    source = _invoice_snapshot_migration()
    for field in (
        "order_id",
        "invoice_number",
        "status",
        "issued_at",
        "currency",
        "tax_type",
        "seller_snapshot",
        "billing_snapshot",
        "shipping_snapshot",
        "totals_snapshot",
    ):
        assert field in source
    assert "insert into public.invoices" in source


def test_invoice_snapshot_does_not_mutate_invoice_after_insert():
    source = _invoice_snapshot_migration()
    insert_pos = source.index("insert into public.invoices")
    invoice_item_pos = source.index("insert into public.invoice_items")
    between = source[insert_pos:invoice_item_pos]
    assert "update public.invoices" not in between
    assert "delete from public.invoices" not in between


def test_invoice_item_snapshot_captures_compare_price_without_mutating_legacy_rows():
    source = _invoice_snapshot_migration()
    assert "insert into public.invoice_items" in source
    assert "compare_price" in source
    assert "existing invoice_items remain immutable" in source
