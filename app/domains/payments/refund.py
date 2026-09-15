"""Payment-domain refund operations.

Keeps external payment-provider calls inside the payments bounded context while
remaining independent of any single gateway implementation.
"""
from typing import Any, Optional

from starlette.concurrency import run_in_threadpool

from app.integrations.payments.registry import get_payment_provider


async def refund_payment_intent(payment_id: str, provider_key: Optional[str] = None) -> Any:
    """Refund a provider payment reference through the configured provider."""
    if not payment_id or not isinstance(payment_id, str) or not payment_id.strip():
        raise ValueError("Provider payment reference is required")

    # Passing "stripe" preserves the request-scoped provider context used by
    # legacy callers, while explicit providers remain directly addressable.
    provider = get_payment_provider((provider_key or "stripe").strip().lower())
    return await run_in_threadpool(provider.process_refund, payment_id.strip())
