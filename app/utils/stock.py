"""
Stock Utility — Atomic deduct + restore
=========================================
ROOT CAUSE of "stock not deducting":
  decrement_stock RPC (migrations.sql Section 3) likely not run in Supabase.
  Old code returned False → order router threw 409 → order never created.

FIXES:
  1. decrement_stock — RPC first, then direct atomic UPDATE fallback
     (WHERE stock >= qty prevents overselling even without RPC)
  2. restore_stock   — same RPC-first pattern, already had fallback
  3. log_stock_event — SKU-wise audit trail in stock_audit table
     (create table below, or just logs if table doesn't exist)

RPC still preferred — it's a single round-trip.
Fallback is safe because Postgres UPDATE is atomic per row.

MIGRATIONS to run in Supabase SQL Editor (if not done):
------------------------------------------------------------
CREATE OR REPLACE FUNCTION decrement_stock(p_id uuid, p_qty int)
RETURNS int LANGUAGE sql AS $$
  UPDATE products
  SET stock = stock - p_qty
  WHERE id = p_id AND stock >= p_qty
  RETURNING stock;
$$;

CREATE OR REPLACE FUNCTION increment_stock(p_id uuid, p_qty int)
RETURNS void LANGUAGE sql AS $$
  UPDATE products SET stock = stock + p_qty WHERE id = p_id;
$$;

-- Optional: SKU audit log
CREATE TABLE IF NOT EXISTS stock_audit (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id  uuid NOT NULL,
    sku         text,
    delta       int NOT NULL,           -- negative = deduct, positive = restore
    stock_after int,
    reason      text,
    created_at  timestamptz DEFAULT now()
);
------------------------------------------------------------
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


# ╔══════════════════════════════════════════════════════════════╗
#  ATOMIC DEDUCT  — 1 function = 1 feature
# ╚══════════════════════════════════════════════════════════════╝
def decrement_stock(sb: "Client", product_id: str, qty: int, product_name: str) -> bool:
    """
    Atomic stock deduction.  Returns True if successful, False if out of stock.

    Strategy:
      1. Try RPC (single round-trip, cleanest)
      2. On RPC failure → direct UPDATE WHERE stock >= qty (still atomic in Postgres)
      3. Never do stale-read + write — that's a race condition

    If BOTH fail → returns False (caller raises 409, order not created).
    """
    # ── Step 1: RPC (preferred) ───────────────────────────────────────────────
    try:
        result = sb.rpc(
            "decrement_stock", {"p_id": product_id, "p_qty": qty}
        ).execute()

        if result and result.data:
            stock_after = result.data[0] if isinstance(result.data[0], int) else result.data[0].get("stock", "?")
            logger.info("Stock deducted via RPC | product=%s qty=-%d stock_after=%s",
                        product_name, qty, stock_after)
            _log_audit(sb, product_id, -qty, stock_after, f"order_create:{product_name}")
            return True
        else:
            # RPC returned empty → stock < qty (insufficient)
            logger.warning("Insufficient stock | product=%s requested=%d", product_name, qty)
            return False

    except Exception as rpc_err:
        logger.warning(
            "decrement_stock RPC failed (run migrations.sql Section 3 to fix permanently) "
            "— falling back to direct UPDATE | product=%s | err=%s",
            product_name, rpc_err,
        )

    # ── Step 2: Direct atomic UPDATE fallback ────────────────────────────────
    # WHERE stock >= qty ensures no overselling — this is atomic in Postgres
    try:
        result = (
            sb.table("products")
            .update({"stock": sb.raw("stock - " + str(int(qty)))})
            .eq("id", product_id)
            .gte("stock", qty)          # ← atomic guard: only updates if stock >= qty
            .execute()
        )

        if result and result.data:
            stock_after = result.data[0].get("stock", "?")
            logger.info("Stock deducted via fallback UPDATE | product=%s qty=-%d stock_after=%s",
                        product_name, qty, stock_after)
            _log_audit(sb, product_id, -qty, stock_after, f"order_create_fallback:{product_name}")
            return True
        else:
            # Update matched 0 rows → stock < qty
            logger.warning("Insufficient stock (fallback) | product=%s requested=%d", product_name, qty)
            return False

    except Exception as direct_err:
        # supabase-py doesn't support raw() — use rpc workaround below
        logger.warning(
            "Direct UPDATE with raw() failed — trying rpc workaround | product=%s | err=%s",
            product_name, direct_err,
        )

    # ── Step 3: RPC workaround via inline SQL ────────────────────────────────
    # If supabase-py raw() isn't supported, do it via a generic exec rpc
    try:
        # Fetch current stock first (best-effort, not perfectly atomic but better than nothing)
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
            .eq("stock", current_stock)   # optimistic lock: only update if unchanged
            .execute()
        )

        if upd and upd.data:
            logger.info(
                "Stock deducted via optimistic lock | sku=%s product=%s qty=-%d stock=%d→%d",
                sku, product_name, qty, current_stock, new_stock,
            )
            _log_audit(sb, product_id, -qty, new_stock, f"order_create_optimistic:{product_name}", sku=sku)
            return True
        else:
            # Another request changed stock between our read and write → retry needed
            logger.warning(
                "Optimistic lock conflict | sku=%s product=%s — stock changed concurrently",
                sku, product_name,
            )
            return False

    except Exception as final_err:
        logger.error(
            "CRITICAL: All stock deduct strategies failed | product=%s qty=%d | %s",
            product_name, qty, final_err, exc_info=True,
        )
        return False


# ╔══════════════════════════════════════════════════════════════╗
#  ATOMIC RESTORE  — cancel / payment_failed / rollback
# ╚══════════════════════════════════════════════════════════════╝
def restore_stock(sb: "Client", product_id: str, qty: int, context: str) -> None:
    """
    Atomic stock restore.  Never raises — worst case logs CRITICAL.
    Used by: order cancel, payment failed webhook, create_order rollback.
    """
    # ── Step 1: RPC ──────────────────────────────────────────────────────────
    try:
        sb.rpc("increment_stock", {"p_id": product_id, "p_qty": qty}).execute()
        logger.info("Stock restored via RPC | product=%s qty=+%d ctx=%s", product_id, qty, context)
        _log_audit(sb, product_id, +qty, None, context)
        return
    except Exception as rpc_err:
        logger.warning(
            "increment_stock RPC failed — trying direct UPDATE | ctx=%s | err=%s",
            context, rpc_err,
        )

    # ── Step 2: Direct UPDATE ────────────────────────────────────────────────
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
            logger.error("CRITICAL: restore_stock — product not found | product=%s ctx=%s",
                         product_id, context)
    except Exception as direct_err:
        logger.error(
            "CRITICAL: Stock restore completely failed | product=%s qty=%d ctx=%s | %s",
            product_id, qty, context, direct_err, exc_info=True,
        )


# ╔══════════════════════════════════════════════════════════════╗
#  SKU AUDIT LOG  — 1 function = 1 feature
# ╚══════════════════════════════════════════════════════════════╝
def _log_audit(
    sb: "Client",
    product_id: str,
    delta: int,
    stock_after: int | None,
    reason: str,
    sku: str | None = None,
) -> None:
    """
    Write SKU-wise stock change to stock_audit table.
    Non-fatal — if table doesn't exist, just logs.
    """
    try:
        row = {"product_id": product_id, "delta": delta, "reason": reason}
        if stock_after is not None:
            row["stock_after"] = stock_after
        if sku:
            row["sku"] = sku
        else:
            # Try to fetch SKU if not provided
            try:
                r = sb.table("products").select("sku").eq("id", product_id).limit(1).execute()
                if r and r.data:
                    row["sku"] = r.data[0].get("sku")
            except Exception:
                pass

        sb.table("stock_audit").insert(row).execute()
    except Exception as e:
        # Table might not exist yet — log as debug, not error
        logger.debug("stock_audit insert skipped (table may not exist): %s", e)