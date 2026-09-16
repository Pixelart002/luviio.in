"""Atomic transaction helpers for durable application event outbox."""
from __future__ import annotations

from typing import Any

from app.core.supabase import get_async_admin_supabase


async def enqueue_event_in_transaction(
    *,
    transaction_rpc: str,
    transaction_args: dict[str, Any],
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> Any:
    """Call a domain RPC that commits its business mutation and outbox row atomically.

    The RPC must insert into public.event_outbox before returning. This helper
    keeps the contract explicit and prevents callers from treating a separate
    post-commit insert as transactional.
    """
    sb = await get_async_admin_supabase()
    args = dict(transaction_args)
    args.update(
        {
            "p_event_id": event_id,
            "p_event_type": event_type,
            "p_event_payload": payload,
        }
    )
    return await sb.rpc(transaction_rpc, args).execute()
