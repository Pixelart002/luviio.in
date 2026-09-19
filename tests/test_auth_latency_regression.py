from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_successful_login_moves_throttle_reset_off_critical_path():
    source = _read("app/domains/auth/service.py")
    assert "background_tasks.add_task(AuthPolicy.reset_attempts, client_ip, email)" in source
    assert "await AuthPolicy.reset_attempts(client_ip, email)" in source


def test_login_router_supplies_background_tasks():
    source = _read("app/domains/auth/router.py")
    assert "background_tasks: BackgroundTasks" in source
    assert "background_tasks=background_tasks" in source


def test_auth_profile_cache_is_present():
    source = _read("app/core/dependencies.py")
    assert "_profile_cache: TTLCache" in source
    assert "if user_id in _profile_cache:" in source
