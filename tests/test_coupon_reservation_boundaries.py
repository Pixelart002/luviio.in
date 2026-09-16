from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _reservation_migration() -> str:
    matches = sorted(
        (REPO_ROOT / "migrations").glob("*atomic_coupon_reservation*.sql")
    )
    assert matches, "atomic coupon reservation migration is missing"
    return matches[-1].read_text(encoding="utf-8").lower()


def test_coupon_reservation_is_atomic_and_service_role_only():
    source = _reservation_migration()
    assert "reserve_coupon" in source
    assert "on conflict" in source
    assert "service_role" in source


def test_coupon_reservation_expiry_cleanup_is_server_only():
    source = _reservation_migration()
    assert "cleanup_expired_coupon_reservations" in source
    assert "revoke execute on function public.cleanup_expired_coupon_reservations() from public, anon, authenticated" in source
    assert "grant execute on function public.cleanup_expired_coupon_reservations() to service_role" in source
