"""
Stock Utility — Atomic Deduct + Restore
========================================
Architecture Layer: Services (Domain Logic)
Path: app/services/stock.py
"""
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
MAX_RETRIES = 3           # Retry on optimistic lock conflict
RETRY_DELAY_SEC = 0.5     # Base delay (doubles each retry)

# ══════════════════════════════════════════════════════════════════════════════
#  ATOMIC STOCK DEDUCTION
# ══════════════════════════════════════════════════════════════════════════════

def decrement_stock(
    sb: "Client",
    product_id: str,
    qty: int,
    product_name: str = "Unknown",
    *,
    max_retries: int = MAX_RETRIES,
) -> bool:
    for attempt in range(1, max_retries + 1):
        # ── Strategy 1: RPC ───────────────────────────────────────────────────
        try:
            result = sb.rpc(
                "decrement_stock",
                {"p_id": product_id, "p_qty": qty}
            ).execute()

            data = result.data if result and hasattr(result, "data") else None

            if data is None:
                logger.warning("Insufficient stock (RPC None) | product=%s qty=%d attempt=%d", product_name, qty, attempt)
                return False

            if isinstance(data, int):
                stock_after = data
            elif isinstance(data, list):
                if len(data) == 0:
                    logger.warning("Insufficient stock (RPC empty) | product=%s qty=%d", product_name, qty)
                    return False
                item = data[0]
                stock_after = item if isinstance(item, int) else item.get("stock", None)
            else:
                stock_after = data.get("stock") if isinstance(data, dict) else None

            if stock_after is not None and stock_after >= 0:
                logger.info("Stock deducted via RPC | product=%s qty=-%d stock_after=%s attempt=%d", product_name, qty, stock_after, attempt)
                _log_audit(sb, product_id, -qty, stock_after, f"order_create:{product_name}")
                return True

        except Exception as rpc_err:
            logger.debug("RPC failed (attempt %d) | product=%s: %s", attempt, product_name, rpc_err)

        # ── Strategy 2: Optimistic lock ────────────────────────────────────────
        try:
            row = sb.table("products").select("id, stock, sku").eq("id", product_id).limit(1).execute()

            if not row or not hasattr(row, "data") or not row.data:
                logger.error("Product not found | product_id=%s", product_id)
                return False

            current = row.data[0]
            current_stock = current.get("stock", 0)
            sku = current.get("sku", "N/A")

            if current_stock < qty:
                logger.warning("Insufficient stock (lock) | sku=%s product=%s current=%d needed=%d", sku, product_name, current_stock, qty)
                return False

            new_stock = current_stock - qty

            upd = (
                sb.table("products")
                .update({"stock": new_stock})
                .eq("id", product_id)
                .eq("stock", current_stock)  # ← Optimistic lock condition
                .execute()
            )

            if upd and hasattr(upd, "data") and upd.data:
                logger.info("Stock deducted via lock | sku=%s product=%s qty=-%d %d→%d attempt=%d", sku, product_name, qty, current_stock, new_stock, attempt)
                _log_audit(sb, product_id, -qty, new_stock, f"order_create_lock:{product_name}", sku=sku)
                return True

            if attempt < max_retries:
                delay = RETRY_DELAY_SEC * (2 ** (attempt - 1))
                logger.warning("Lock conflict (attempt %d/%d) | sku=%s — retrying in %.1fs", attempt, max_retries, sku, delay)
                time.sleep(delay)
                continue
            else:
                logger.error("Lock conflict exhausted | sku=%s product=%s", sku, product_name)
                return False

        except Exception as lock_err:
            logger.debug("Optimistic lock failed (attempt %d) | product=%s: %s", attempt, product_name, lock_err)
            if attempt < max_retries:
                time.sleep(RETRY_DELAY_SEC * (2 ** (attempt - 1)))

    logger.error("CRITICAL: All stock deduct strategies failed | product=%s qty=%d", product_name, qty)
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  ATOMIC STOCK RESTORE
# ══════════════════════════════════════════════════════════════════════════════

def restore_stock(sb: "Client", product_id: str, qty: int, context: str = "unknown") -> bool:
    try:
        sb.rpc("increment_stock", {"p_id": product_id, "p_qty": qty}).execute()
        logger.info("Stock restored via RPC | product=%s qty=+%d ctx=%s", product_id, qty, context)
        _log_audit(sb, product_id, +qty, None, context)
        return True
    except Exception as rpc_err:
        logger.warning("RPC restore failed — trying UPDATE | ctx=%s: %s", context, rpc_err)

    try:
        row = sb.table("products").select("stock").eq("id", product_id).limit(1).execute()

        if row and hasattr(row, "data") and row.data:
            current_stock = row.data[0].get("stock", 0)
            new_stock = current_stock + qty
            sb.table("products").update({"stock": new_stock}).eq("id", product_id).execute()
            logger.info("Stock restored via UPDATE | product=%s qty=+%d %d→%d ctx=%s", product_id, qty, current_stock, new_stock, context)
            _log_audit(sb, product_id, +qty, new_stock, context)
            return True
        else:
            logger.error("CRITICAL: restore_stock — product not found | product=%s ctx=%s", product_id, context)
            return False
    except Exception as direct_err:
        logger.error("CRITICAL: Stock restore completely failed | product=%s qty=%d ctx=%s: %s", product_id, qty, context, direct_err, exc_info=True)
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  BATCH & UTILS
# ══════════════════════════════════════════════════════════════════════════════

def decrement_stock_batch(sb: "Client", items: list[tuple[str, int, str]]) -> tuple[list[str], list[str]]:
    succeeded_items = []
    failed_ids = []

    for product_id, qty, name in items:
        if decrement_stock(sb, product_id, qty, name):
            succeeded_items.append((product_id, qty, name))
        else:
            failed_ids.append(product_id)
            for sid, sqty, sname in succeeded_items:
                restore_stock(sb, sid, sqty, f"batch_rollback:{sname}")
            return [], [product_id] 

    return [item[0] for item in succeeded_items], failed_ids

def restore_stock_batch(sb: "Client", items: list[tuple[str, int, str]]) -> int:
    restored = 0
    for product_id, qty, context in items:
        if restore_stock(sb, product_id, qty, context):
            restored += 1
    return restored

def get_stock(sb: "Client", product_id: str) -> int | None:
    try:
        row = sb.table("products").select("stock").eq("id", product_id).limit(1).execute()
        if row and hasattr(row, "data") and row.data:
            return row.data[0].get("stock", 0)
        return None
    except Exception as exc:
        logger.error("get_stock failed | product=%s: %s", product_id, exc)
        return None

def is_in_stock(sb: "Client", product_id: str, qty: int = 1) -> bool:
    stock = get_stock(sb, product_id)
    return stock is not None and stock >= qty

def _log_audit(sb: "Client", product_id: str, delta: int, stock_after: int | None, reason: str, sku: str | None = None) -> None:
    try:
        row = {"product_id": product_id, "delta": delta, "reason": reason[:200]}
        if stock_after is not None: row["stock_after"] = stock_after
        if sku:
            row["sku"] = sku
        else:
            try:
                r = sb.table("products").select("sku").eq("id", product_id).limit(1).execute()
                if r and hasattr(r, "data") and r.data: row["sku"] = r.data[0].get("sku")
            except Exception: pass
        sb.table("stock_audit").insert(row).execute()
    except Exception as exc:
        logger.debug("Stock audit skipped (table may not exist): %s", exc)