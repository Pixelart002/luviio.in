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



def test_invoice_asset_repair_patches_live_function_without_mutating_issued_invoices():
    source = (
        REPO_ROOT
        / "migrations"
        / "20261017171520_fix_invoice_snapshot_business_asset_urls.sql"
    ).read_text(encoding="utf-8").lower()

    assert "pg_get_functiondef" in source
    assert "execute patched_definition" in source
    assert "'business_logo_url'" in source
    assert "'business_signature_url'" in source
    assert "'logo_url',nullif(v_logo_url,'')" in source
    assert "'signature_url',nullif(v_signature_url,'')" in source
    assert "'compare_price',round(coalesce(oi.compare_price,0),2)" in source
    assert "shipping-tax allocation" in source
    assert "update public.invoices" not in source


def test_invoice_asset_repair_fails_closed_when_live_function_anchors_drift():
    source = (
        REPO_ROOT
        / "migrations"
        / "20261017171520_fix_invoice_snapshot_business_asset_urls.sql"
    ).read_text(encoding="utf-8").lower()

    assert "declaration anchor was not unique" in source
    assert "settings-read anchor was not unique" in source
    assert "snapshot json anchor was not unique" in source
    assert "compare-price anchor was not unique" in source
