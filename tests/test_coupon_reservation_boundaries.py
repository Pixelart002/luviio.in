from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPO_ROOT / "migrations"


def _reservation_migration() -> str:
    path = MIGRATIONS / "20260916190000_atomic_coupon_reservation_and_expiry_cleanup.sql"
    assert path.exists(), "atomic coupon reservation migration is missing"
    return path.read_text(encoding="utf-8").lower()


def test_coupon_reservation_is_atomic_and_service_role_only():
    source = _reservation_migration()
    assert "create_pending_order_with_reservation" in source
    assert "reserve_coupon_for_order" in source
    assert "if coalesce(v_coupon_reserved,false) = false" in source
    assert "revoke all on function public.create_pending_order_with_reservation" in source
    assert "grant execute on function public.create_pending_order_with_reservation" in source


def test_coupon_reservation_expiry_cleanup_is_server_only():
    source = _reservation_migration()
    assert "cleanup_expired_coupon_reservations" in source
    assert "revoke execute on function public.cleanup_expired_coupon_reservations() from public, anon, authenticated" in source
    assert "grant execute on function public.cleanup_expired_coupon_reservations() to service_role" in source
