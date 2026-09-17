"""Inventory-side settlement for customer cancellations."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.supabase import get_async_admin_supabase


async def release_stock_for_customer_cancellation(
    order_id: str,
    user_id: Optional[str] = None,
    target_status: str = "cancelled",
) -> Optional[Dict[str, Any]]:
    """Release order stock and atomically move the order to its settlement status."""
    if target_status not in {"cancelled", "refunded"}:
        return None

    admin_sb = await get_async_admin_supabase()
    reason = "customer_requested" if user_id else "admin_requested"
    res = await admin_sb.rpc(
        "cancel_order_and_release_stock",
        {
            "p_order_id": order_id,
            "p_reason": reason,
            "p_target_status": target_status,
        },
    ).execute()
    result = str(getattr(res, "data", "FAILED"))
    if result not in {"CANCELLED", "REFUNDED", "ALREADY_CANCELLED"}:
        return None

    updated = await admin_sb.table("orders").select("*").eq("id", order_id).maybe_single().execute()
    return getattr(updated, "data", None)
