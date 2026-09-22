from types import SimpleNamespace

from app.integrations.push import webpush_impl


def test_shared_push_guard_calls_service_role_rpc(monkeypatch):
    calls = []

    class RPC:
        def __init__(self, name, params):
            calls.append((name, params))

        def execute(self):
            return SimpleNamespace(data=True)

    class Client:
        def rpc(self, name, params):
            return RPC(name, params)

    monkeypatch.setattr(webpush_impl, "get_admin_supabase", lambda: Client())

    assert webpush_impl._shared_push_guard("endpoint-key") is True
    assert calls == [
        (
            "push_delivery_guard",
            {
                "p_endpoint_key": "endpoint-key",
                "p_limit": 3,
                "p_window_seconds": 1,
                "p_failure_threshold": 5,
                "p_reset_seconds": 60,
            },
        )
    ]


def test_shared_push_guard_fails_closed_when_storage_unavailable(monkeypatch):
    def broken_client():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(webpush_impl, "get_admin_supabase", broken_client)

    assert webpush_impl._shared_push_guard("endpoint-key") is False


def test_push_success_and_failure_persist_shared_state(monkeypatch):
    calls = []

    class RPC:
        def __init__(self, name, params):
            calls.append((name, params))

        def execute(self):
            return SimpleNamespace(data=None)

    class Client:
        def rpc(self, name, params):
            return RPC(name, params)

    monkeypatch.setattr(webpush_impl, "get_admin_supabase", lambda: Client())

    webpush_impl._record_push_success("ok-key")
    webpush_impl._record_push_failure("failed-key")

    assert calls[0] == ("push_delivery_record_success", {"p_endpoint_key": "ok-key"})
    assert calls[1] == (
        "push_delivery_record_failure",
        {
            "p_endpoint_key": "failed-key",
            "p_failure_threshold": 5,
            "p_reset_seconds": 60,
        },
    )
