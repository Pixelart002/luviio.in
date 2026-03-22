"""
Stock Utility - Atomic deduct + restore
FIX: RPC result.data can be a raw int (not a list) - handle both cases
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


def decrement_stock(sb: "Client", product_id: str, qty: int, product_name: str) -> bool:
    """
    Atomic stock deduction. Returns True on success, False if insufficient stock.
    Strategy: RPC -> direct UPDATE fallback -> optimistic lock fallback
    """
    # Step 1: RPC (preferred - single round trip)
    try:
        result = sb.rpc(
            "decrement_stock", {"p_id": product_id, "p_qty": qty}
        ).execute()

        # FIX: result.data can be:
        #   - int directly (e.g. 19) when RPC returns scalar
        #   - list of ints (e.g. [19])
        #   - list of dicts (e.g. [{"stock": 19}])
        #   - empty list [] when WHERE stock >= qty didn't match
        #   - None when RPC fails silently
        data = result.data if result else None

        if data is None:
            logger.warning("Insufficient stock (RPC None) | product=%s", product_name)
            return False

        if isinstance(data, int):
            # Scalar int returned directly
            stock_after = data
        elif isinstance(data, list) and len(data) > 0:
            item = data[0]
            stock_after = item if isinstance(item, int) else item.get("stock", "?")
        elif isinstance(data, list) and len(data) == 0:
            # Empty list = WHERE stock >= qty didn't match = insufficient
            logger.warning("Insufficient stock (RPC empty) | product=%s requested=%d", product_name, qty)
            return False
        else:
            stock_after = "?"

        logger.info("Stock deducted via RPC | product=%s qty=-%d stock_after=%s",
                    product_name, qty, stock_after)
        _log_audit(sb, product_id, -qty, stock_after, f"order_create:{product_name}")
        return True

    except Exception as rpc_err:
        logger.warning(
            "decrement_stock RPC failed - falling back to direct UPDATE | product=%s | err=%s",
            product_name, rpc_err,
        )

    # Step 2: Direct atomic UPDATE fallback (WHERE stock >= qty is atomic in Postgres)
    try:
        result = (
            sb.table("products")
            .update({"stock": sb.raw("stock - " + str(int(qty)))})
            .eq("id", product_id)
            .gte("stock", qty)
            .execute()
        )
        if result and result.data:
            stock_after = result.data[0].get("stock", "?")
            logger.info("Stock deducted via fallback UPDATE | product=%s qty=-%d stock_after=%s",
                        product_name, qty, stock_after)
            _log_audit(sb, product_id, -qty, stock_after, f"order_create_fallback:{product_name}")
            return True
        else:
            logger.warning("Insufficient stock (fallback) | product=%s requested=%d", product_name, qty)
            return False
    except Exception as direct_err:
        logger.warning(
            "Direct UPDATE with raw() failed - trying optimistic lock | product=%s | err=%s",
            product_name, direct_err,
        )

    # Step 3: Optimistic lock fallback
    try:
        row = (
            sb.table("products")
            .select("id, stock, sku")
            .eq("id", product_id)
            .limit(1)
            .execute()
        )
        if not row.data:
            logger.error("Product not found for stock deduct | product_id=%s", product_id)
            return False

        current = row.data[0]
        current_stock = current.get("stock", 0)
        sku = current.get("sku", "N/A")

        if current_stock < qty:
            logger.warning(
                "Insufficient stock | sku=%s product=%s current=%d requested=%d",
                sku, product_name, current_stock, qty,
            )
            return False

        new_stock = current_stock - qty
        upd = (
            sb.table("products")
            .update({"stock": new_stock})
            .eq("id", product_id)
            .eq("stock", current_stock)
            .execute()
        )
        if upd and upd.data:
            logger.info(
                "Stock deducted via optimistic lock | sku=%s product=%s qty=-%d stock=%d->%d",
                sku, product_name, qty, current_stock, new_stock,
            )
            _log_audit(sb, product_id, -qty, new_stock, f"order_create_optimistic:{product_name}", sku=sku)
            return True
        else:
            logger.warning(
                "Optimistic lock conflict | sku=%s product=%s - stock changed concurrently",
                sku, product_name,
            )
            return False

    except Exception as final_err:
        logger.error(
            "CRITICAL: All stock deduct strategies failed | product=%s qty=%d | %s",
            product_name, qty, final_err, exc_info=True,
        )
        return False


def restore_stock(sb: "Client", product_id: str, qty: int, context: str) -> None:
    """
    Atomic stock restore. Never raises.
    Used by: order cancel, payment failed webhook, create_order rollback.
    """
    # Step 1: RPC
    try:
        sb.rpc("increment_stock", {"p_id": product_id, "p_qty": qty}).execute()
        logger.info("Stock restored via RPC | product=%s qty=+%d ctx=%s", product_id, qty, context)
        _log_audit(sb, product_id, +qty, None, context)
        return
    except Exception as rpc_err:
        logger.warning(
            "increment_stock RPC failed - trying direct UPDATE | ctx=%s | err=%s",
            context, rpc_err,
        )

    # Step 2: Direct UPDATE
    try:
        row = (
            sb.table("products")
            .select("stock")
            .eq("id", product_id)
            .limit(1)
            .execute()
        )
        if row and row.data:
            new_stock = row.data[0]["stock"] + qty
            sb.table("products").update({"stock": new_stock}).eq("id", product_id).execute()
            logger.info("Stock restored via direct UPDATE | product=%s qty=+%d stock_after=%d ctx=%s",
                        product_id, qty, new_stock, context)
            _log_audit(sb, product_id, +qty, new_stock, context)
        else:
            logger.error("CRITICAL: restore_stock - product not found | product=%s ctx=%s",
                         product_id, context)
    except Exception as direct_err:
        logger.error(
            "CRITICAL: Stock restore completely failed | product=%s qty=%d ctx=%s | %s",
            product_id, qty, context, direct_err, exc_info=True,
        )


def _log_audit(
    sb: "Client",
    product_id: str,
    delta: int,
    stock_after,
    reason: str,
    sku: str = None,
) -> None:
    """Write stock change to stock_audit table. Non-fatal."""
    try:
        row = {"product_id": product_id, "delta": delta, "reason": reason}
        if stock_after is not None:
            row["stock_after"] = stock_after
        if sku:
            row["sku"] = sku
        else:
            try:
                r = sb.table("products").select("sku").eq("id", product_id).limit(1).execute()
                if r and r.data:
                    row["sku"] = r.data[0].get("sku")
            except Exception:
                pass
        sb.table("stock_audit").insert(row).execute()
    except Exception as e:
        logger.debug("stock_audit insert skipped (table may not exist or no permission): %s", e)