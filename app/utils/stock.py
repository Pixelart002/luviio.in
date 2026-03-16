import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


def restore_stock(sb: "Client", product_id: str, qty: int, context: str) -> None:
    """
    Atomic stock restore via RPC.
    Fallback: direct update agar RPC nahi hai (less atomic lekin better than nothing).
    Cancel, rollback, payment_failed — sab jagah use hota hai.
    """
    try:
        sb.rpc("increment_stock", {"p_id": product_id, "p_qty": qty}).execute()
    except Exception as rpc_err:
        logger.warning(
            "RPC increment_stock failed [%s] — trying direct update. "
            "Run migrations.sql to fix permanently: %s",
            context, rpc_err,
        )
        try:
            row = (
                sb.table("products")
                .select("stock")
                .eq("id", product_id)
                .single()
                .execute()
            )
            if row.data:
                sb.table("products").update(
                    {"stock": row.data["stock"] + qty}
                ).eq("id", product_id).execute()
        except Exception as direct_err:
            logger.error(
                "CRITICAL: Stock restore completely failed [%s] product=%s qty=%d err=%s",
                context, product_id, qty, direct_err,
            )


def decrement_stock(sb: "Client", product_id: str, qty: int, product_name: str) -> bool:
    """
    Atomic stock decrement via DB RPC.
    Returns True if successful, False if insufficient stock.

    NO fallback here — stale read race condition se bachao.
    Agar RPC fail ho toh False return karo, caller ko pata chale migrations nahi hua.
    """
    try:
        result = sb.rpc(
            "decrement_stock", {"p_id": product_id, "p_qty": qty}
        ).execute()
        # RPC returns remaining stock row — empty = insufficient stock
        return bool(result.data)
    except Exception as e:
        logger.error(
            "decrement_stock RPC failed for '%s' — migrations.sql run karo: %s",
            product_name, e,
        )
        # Fail safely — do NOT do stale-read fallback (race condition)
        return False