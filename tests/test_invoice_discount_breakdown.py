from pathlib import Path

from app.utils.documents.invoice_pdf_renderer import _discount_breakdown


def test_invoice_keeps_membership_and_coupon_discounts_separate():
    assert _discount_breakdown(
        {
            "discount_amount": 125.0,
            "membership_discount_amount": 75.0,
            "coupon_discount_amount": 50.0,
        }
    ) == [
        ("Membership discount", 75.0),
        ("Coupon discount", 50.0),
    ]


def test_invoice_prints_membership_discount_without_a_coupon():
    assert _discount_breakdown(
        {"discount_amount": 75.0, "membership_discount_amount": 75.0}
    ) == [("Membership discount", 75.0)]


def test_invoice_keeps_generic_discount_for_legacy_snapshots():
    # Older immutable snapshots may contain only the aggregate discount.
    # Do not guess whether a legacy amount was a membership or coupon discount.
    assert _discount_breakdown({"discount_amount": 25.0}) == [("Discount", 25.0)]


def test_invoice_shows_only_the_unclassified_residual_after_split_discounts():
    assert _discount_breakdown(
        {
            "discount_amount": 135.0,
            "membership_discount_amount": 75.0,
            "coupon_discount_amount": 50.0,
        }
    ) == [
        ("Membership discount", 75.0),
        ("Coupon discount", 50.0),
        ("Discount", 10.0),
    ]


def test_snapshot_migration_captures_both_discount_components():
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "20261024120000_invoice_discount_breakdown.sql"
    ).read_text(encoding="utf-8")
    assert "membership_discount_amount" in migration
    assert "membership_discount_percent" in migration
    assert "coupon_discount_amount" in migration
    assert "already-issued invoice rows remain untouched" in migration
