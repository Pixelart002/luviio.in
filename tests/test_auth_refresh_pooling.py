import pytest

from app.domains.auth import repository as auth_repository


class _FakeResponse:
    status_code = 200
    text = ""

    def json(self) -> dict:
        return {
            "user": {"id": "user-1", "email": "user@example.com"},
            "access_token": "access-token",
            "refresh_token": "rotated-refresh-token",
            "expires_in": 3600,
        }


class _FakeClient:
    def __init__(self) -> None:
        self.post_calls = 0

    async def post(self, url: str, **kwargs):
        self.post_calls += 1
        assert url.endswith("/auth/v1/token?grant_type=refresh_token")
        assert kwargs["json"] == {"refresh_token": "refresh-token"}
        return _FakeResponse()


@pytest.mark.asyncio
async def test_refresh_session_uses_shared_auth_http_client(monkeypatch) -> None:
    client = _FakeClient()
    monkeypatch.setattr(auth_repository, "get_auth_http_client", lambda: _completed_client(client))

    result = await auth_repository.AsyncAuthRepository().refresh_session("refresh-token")

    assert result["user_id"] == "user-1"
    assert result["refresh_token"] == "rotated-refresh-token"
    assert client.post_calls == 1


async def _completed_client(client: _FakeClient):
    return client
