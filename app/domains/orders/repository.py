"""
Order Repository — Async Enterprise Grade.

Customer order history uses a lightweight summary projection; full order items
remain available through get_order_by_id for the order-detail view.
"""
import logging
from typing import Any, List, Optional, Tuple
from uuid import UUID

from app.core.supabase import get_async_admin_supabase
from app.domains.orders.exceptions import OrderRepositoryError

logger = logging.getLogger(__name__)

ORDER_ITEMS_SELECT = "*, order_items(*, products(name, image_url, slug, price, hsn_code, gst_percentage, compare_price))"
USER_ORDER_SELECT = "id, order_number, status, total_amount, created_at"
INVOICE_SELECT = "id, order_id, invoice_number, status, issued_at, currency, tax_type, seller_snapshot, billing_snapshot, shipping_snapshot, totals_snapshot, pdf_storage_path, qr_payload, invoice_items(*)"


class AsyncOrderRepository:
    async def get_order_by_id(self, order_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Resolve either an internal UUID (server-side) or the existing order_number."""
        admin_sb = await get_async_admin_supabase()
        try:
            q = admin_sb.table("orders").select(ORDER_ITEMS_SELECT)
            try:
                UUID(str(order_id))
                q = q.eq("id", str(order_id))
            except (ValueError, TypeError):
                q = q.eq("order_number", str(order_id))
            if user_id:
                q = q.eq("customer_id", user_id)
            res = await q.maybe_single().execute()
            return res.data if res else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed to resolve order reference: {e}", exc_info=True)
            return None

    async def get_invoice_snapshot(self, order_id: str) -> Optional[dict[str, Any]]:
        """Return immutable invoice data, enriching legacy lines only when compare price was not snapshotted."""
        admin_sb = await get_async_admin_supabase()
        try:
            res = await (
                admin_sb.table("invoices")
                .select(INVOICE_SELECT)
                .eq("order_id", order_id)
                .maybe_single()
                .execute()
            )
            if not res or not res.data:
                return None
            invoice = res.data
            invoice_items = invoice.get("invoice_items") or []
            if invoice_items:
                legacy_lines = [
                    item for item in invoice_items
                    if not item.get("compare_price")
                    and not (_metadata_compare_price(item))
                ]
                if legacy_lines:
                    order_items_res = await (
                        admin_sb.table("order_items")
                        .select("id, compare_price")
                        .eq("order_id", order_id)
                        .execute()
                    )
                    compare_by_id = {
                        str(row.get("id")): row.get("compare_price")
                        for row in (order_items_res.data or [])
                        if row.get("id") is not None
                    }
                    for item in invoice_items:
                        metadata = item.get("metadata") or {}
                        source_id = str(metadata.get("source_order_item_id") or "")
                        if not _metadata_compare_price(item) and not item.get("compare_price") and source_id in compare_by_id:
                            item["compare_price"] = compare_by_id[source_id]
                for item in invoice_items:
                    metadata = item.get("metadata") or {}
                    if not item.get("compare_price") and _metadata_compare_price(item):
                        item["compare_price"] = _metadata_compare_price(item)
                invoice["invoice_items"] = invoice_items
            return invoice
        except Exception as e:
            logger.error(f"[REPO:INVOICES] Failed loading invoice snapshot for order {order_id}: {e}", exc_info=True)
            return None

    async def update_order_status_safe(self, order_id: str, updates: dict, expected_status: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            check = await admin_sb.table("orders").select("id").eq("id", order_id).eq("status", expected_status).execute()
            if not check or not check.data:
                return None
            res = await admin_sb.rpc("rpc_admin_update_order_status", {"p_order_id": order_id, "p_new_status": updates.get("status"), "p_tracking_number": updates.get("tracking_number"), "p_notes": updates.get("notes")}).execute()
            return res.data if res and res.data else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error updating order {order_id}: {e}", exc_info=True)
            return None

    async def get_user_orders(self, user_id: str, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        admin_sb = await get_async_admin_supabase()
        offset = (page - 1) * page_size
        try:
            q = admin_sb.table("orders").select(USER_ORDER_SELECT, count="exact").eq("customer_id", user_id).order("created_at", desc=True)
            if status_filter:
                q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed fetching user orders: {e}", exc_info=True)
            raise OrderRepositoryError("Unable to load order history right now.") from e

    async def get_all_orders(self, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        admin_sb = await get_async_admin_supabase()
        offset = (page - 1) * page_size
        try:
            q = admin_sb.table("orders").select(f"{ORDER_ITEMS_SELECT}, users(email, full_name)", count="exact").order("created_at", desc=True)
            if status_filter:
                q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed fetching all orders: {e}", exc_info=True)
            raise OrderRepositoryError("Unable to load orders right now.") from e

    async def get_order_for_admin_update(self, order_id: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("status, stripe_payment_intent, customer_id").eq("id", order_id).maybe_single().execute()
            return res.data if res else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error fetching order for admin update {order_id}: {e}", exc_info=True)
            return None

    async def get_user_email(self, user_id: str) -> Optional[str]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
            return res.data["email"] if res and res.data else None
        except Exception:
            return None


def _metadata_compare_price(item: dict[str, Any]) -> Any:
    metadata = item.get("metadata") or {}
    value = metadata.get("compare_price")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
