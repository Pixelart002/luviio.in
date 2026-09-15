"""Request-scoped payment provider selection.

The legacy PaymentService API defaults to Stripe for backward compatibility.
Routers can set a provider key before constructing the service so the same
application service can execute against another installed provider without
hard-coding provider selection into the domain service.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_provider_key: ContextVar[str | None] = ContextVar("luviio_payment_provider", default=None)


def get_current_provider_key(default: str = "stripe") -> str:
    return (_provider_key.get() or default).strip().lower()


@contextmanager
def payment_provider_context(provider_key: str | None) -> Iterator[None]:
    key = provider_key.strip().lower() if provider_key else None
    token = _provider_key.set(key)
    try:
        yield
    finally:
        _provider_key.reset(token)
