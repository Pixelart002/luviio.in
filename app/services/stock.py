"""
Stock Utility — Async Atomic Deduct + Restore
=============================================
Path: app/services/stock.py
"""
import logging
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SEC = 0.5

async def decrement_stock(
    sb: "AsyncClient",
    product_id: str,
    qty: int,
    product_name: str = "Unknown",
    *,
    max_retries: int = MAX_RETRIES,
) -> bool:
    """Decrements stock using RPC first, falling back to Optimistic Locking."""
    for attempt in range(1, max_retries + 1):
        # -- Strategy 1: RPC --
        try:
            result = await sb.rpc("decrement_stock", {"p_id": product_id, "p_qty": qty}).execute()
            data = result.data if result and hasattr(result, "data") else None

            if data is None or (isinstance(data, list) and len(data) == 0):
                return False

            stock_after = data if isinstance(data, int) else (data[0].get("stock") if isinstance(data, list) else data.get("stock"))
            
            if stock_after is not None and stock_after >= 0:
                await _log_audit(sb, product_id, -qty, stock_after, f"order_create:{product_name}")
                return True
        except Exception as rpc_err:
            logger.debug("RPC failed (attempt %d) | product=%s: %s", attempt, product_name, rpc_err)

        # -- Strategy 2: Optimistic lock --
        try:
            row = await sb.table("products").select("id, stock, sku").eq("id", product_id).limit(1).execute()
            if not row or not getattr(row, "data", None):
                return False

            current = row.data[0]
            current_stock = current.get("stock", 0)

            if current_stock < qty:
                return False

            new_stock = current_stock - qty

            upd = await (
                sb.table("products")
                .update({"stock": new_stock})
                .eq("id", product_id)
                .eq("stock", current_stock)  # Optimistic lock condition
                .execute()
            )

            if upd and getattr(upd, "data", None):
                await _log_audit(sb, product_id, -qty, new_stock, f"order_create_lock:{product_name}", sku=current.get("sku"))
                return True

            if attempt < max_retries:
                delay = RETRY_DELAY_SEC * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
                continue
            else:
                return False

        except Exception as lock_err:
            if attempt < max_retries:
                await asyncio.sleep(RETRY_DELAY_SEC * (2 ** (attempt - 1)))

    return False