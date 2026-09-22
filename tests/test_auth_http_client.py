import pytest

from app.domains.auth.http_client import (
    close_auth_http_client,
    get_auth_http_client,
    init_auth_http_client,
)


@pytest.mark.asyncio
async def test_auth_http_client_is_process_scoped_and_reusable() -> None:
    await close_auth_http_client()

    first = await init_auth_http_client()
    second = await get_auth_http_client()

    assert first is second
    assert not first.is_closed

    await close_auth_http_client()

    assert first.is_closed
