"""Request-scoped shipping provider selection."""
from __future__ import annotations

from contextvars import ContextVar

_provider_key: ContextVar[str | None] = ContextVar("luviio_shipping_provider", default=None)


def get_current_shipping_provider_key(default: str = "shiprocket") -> str:
    return (_provider_key.get() or default).strip().lower()


def set_shipping_provider_key(provider_key: str | None):
    return _provider_key.set(provider_key.strip().lower() if provider_key else None)


def reset_shipping_provider_key(token) -> None:
    _provider_key.reset(token)
