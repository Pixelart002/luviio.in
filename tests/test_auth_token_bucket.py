from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_auth_token_bucket_migration_is_shared_and_atomic():
    migration = (
        REPO_ROOT
        / "migrations/20260927090000_auth_token_bucket_throttle.sql"
    ).read_text(encoding="utf-8")

    assert "tokens numeric(12,4)" in migration
    assert "last_refill_at timestamptz" in migration
    assert "v_capacity := p_max_attempts" in migration
    assert "v_refill_interval := GREATEST" in migration
    assert "FOR UPDATE" in migration
    assert "tokens = GREATEST(0, v_available - 1)" in migration
    assert "RETURN false" in migration
    assert "RETURN true" in migration


def test_auth_router_does_not_keep_fixed_window_login_register_limits():
    router = (
        REPO_ROOT / "app/domains/auth/router.py"
    ).read_text(encoding="utf-8")

    assert '@router.post("/login"' in router
    assert '@router.post("/register"' in router
    assert '@limiter.limit("5/minute")' not in router


def test_auth_policy_has_no_legacy_fixed_window_methods():
    policy = (REPO_ROOT / "app/permissions/policies/auth_policies.py").read_text(encoding="utf-8")
    service = (REPO_ROOT / "app/domains/auth/service.py").read_text(encoding="utf-8")
    assert "auth_throttle_record_failure" not in policy
    assert "auth_throttle_reset" not in policy
    assert "AuthPolicy.record_failed_attempt" not in service
    assert "AuthPolicy.reset_attempts" not in service
