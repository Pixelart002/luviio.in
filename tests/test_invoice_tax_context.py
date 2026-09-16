from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _migration() -> str:
    path = MIGRATIONS / "20260916230000_snapshot_place_of_supply_and_rcm.sql"
    assert path.exists(), "invoice tax-context migration is missing"
    return path.read_text(encoding="utf-8").lower()


def test_invoice_tax_context_is_snapshotted_from_order():
    source = _migration()
    assert "add column if not exists reverse_charge boolean not null default false" in source
    assert "add column if not exists place_of_supply_state_code text" in source
    assert "snapshot_invoice_tax_context" in source
    assert "new.place_of_supply_state_code := v_pos_code" in source
    assert "new.reverse_charge := v_reverse_charge" in source


def test_invoice_tax_context_is_immutable_after_insert():
    source = _migration()
    assert "prevent_invoice_tax_context_mutation" in source
    assert "invoice_tax_context_immutable" in source
    assert "trg_prevent_invoice_tax_context_mutation" in source
