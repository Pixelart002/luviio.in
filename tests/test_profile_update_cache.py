"""Regression tests for stale profile cache after self-service edits."""

import asyncio
from types import SimpleNamespace

from app.domains.users.router import get_me
from app.domains.users.service import UserService


def test_self_profile_update_invalidates_cached_profile(monkeypatch):
    updated_profile = {
        "id": "user-123",
        "email": "customer@example.com",
        "full_name": "Updated Name",
        "phone": "9876543210",
        "role": "customer",
    }

    class FakeRepository:
        async def update_profile(self, user_id, data):
            assert user_id == "user-123"
            assert data == {"full_name": "Updated Name"}
            return updated_profile

    invalidated = []
    monkeypatch.setattr(
        "app.core.dependencies.invalidate_profile_cache",
        lambda user_id: invalidated.append(user_id),
    )

    service = UserService()
    service.repo = FakeRepository()

    result = asyncio.run(
        service.update_profile("user-123", {"full_name": "Updated Name"})
    )

    assert result["full_name"] == "Updated Name"
    assert invalidated == ["user-123"]


def test_current_profile_endpoint_reads_authoritative_profile(monkeypatch):
    fresh_profile = {
        "id": "user-123",
        "email": "customer@example.com",
        "full_name": "New Saved Name",
        "phone": "9876543210",
        "role": "customer",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
    }

    class FakeUserService:
        async def get_profile(self, user_id):
            assert user_id == "user-123"
            return fresh_profile

    monkeypatch.setattr("app.domains.users.router.UserService", FakeUserService)

    request = SimpleNamespace(state=SimpleNamespace())
    stale_cached_user = {
        "sub": "user-123",
        "profile": {
            **fresh_profile,
            "full_name": "Old Cached Name",
        },
    }

    result = asyncio.run(get_me(request, stale_cached_user))

    assert result["success"] is True
    assert result["data"]["full_name"] == "New Saved Name"
