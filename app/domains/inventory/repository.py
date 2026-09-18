"""
Inventory Repository
====================
Path: app/domains/inventory/repository.py
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.supabase import get_async_admin_supabase
from app.integrations.payments.context import get_current_provider_key

logger = logging.getLogger(__name__)


class InventoryRepository:
    """Repository for stock and inventory operations."""

    async def get_product_stock_status(self, product_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("products").select(
                "id, name, price, compare_price, stock, hsn_code, gst_percentage, is_active, low_stock_threshold"
            ).eq("id", product_id).limit(1).execute()
            data = getattr(res, "data", None)
            return data[0] if data else None
        except Exception as exc:
            logger.error("DB Error checking stock for product %s: %s", product_id, exc, exc_info=True)
            raise

    async def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("products").select("*").eq("id", product_id).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching product %s: %s", product_id, exc, exc_info=True)
            return None

    async def check_multiple_products_stock(self, product_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("products").select(
                "id, name, stock, is_active, low_stock_threshold"
            ).in_("id", product_ids).execute()
            data = getattr(res, "data", None) or []
            return {item["id"]: item for item in data}
        except Exception as exc:
            logger.error("DB Error checking stock for products %s: %s", product_ids, exc, exc_info=True)
            raise

    async def admin_adjust_stock(self, product_id: str, delta: int, reason: str) -> Dict[str, Any]:
        return await self._inventory_rpc(
            "admin_adjust_stock",
            {"p_product_id": product_id, "p_delta": delta, "p_reason": reason},
        )

    async def inventory_receive_stock(
        self, product_id: str, quantity: int, reason: str, reference_id: Optional[UUID], metadata: dict[str, Any]
    ) -> Dict[str, Any]:
        return await self._inventory_rpc(
            "inventory_receive_stock",
            {"p_product_id": product_id, "p_quantity": quantity, "p_reason": reason,
             "p_reference_id": str(reference_id) if reference_id else None, "p_metadata": metadata},
        )

    async def inventory_record_return(
        self, product_id: str, quantity: int, reason: str, order_id: Optional[UUID], metadata: dict[str, Any]
    ) -> Dict[str, Any]:
        return await self._inventory_rpc(
            "inventory_record_return",
            {"p_product_id": product_id, "p_quantity": quantity, "p_reason": reason,
             "p_order_id": str(order_id) if order_id else None, "p_metadata": metadata},
        )

    async def inventory_record_damage(
        self, product_id: str, quantity: int, reason: str, reference_id: Optional[UUID], metadata: dict[str, Any]
    ) -> Dict[str, Any]:
        return await self._inventory_rpc(
            "inventory_record_damage",
            {"p_product_id": product_id, "p_quantity": quantity, "p_reason": reason,
             "p_reference_id": str(reference_id) if reference_id else None, "p_metadata": metadata},
        )

    async def inventory_record_wastage(
        self, product_id: str, quantity: int, reason: str, reference_id: Optional[UUID], metadata: dict[str, Any]
    ) -> Dict[str, Any]:
        return await self._inventory_rpc(
            "inventory_record_wastage",
            {"p_product_id": product_id, "p_quantity": quantity, "p_reason": reason,
             "p_reference_id": str(reference_id) if reference_id else None, "p_metadata": metadata},
        )

    async def inventory_reconcile_stock(
        self, product_id: str, counted_stock: int, reason: str, metadata: dict[str, Any]
    ) -> Dict[str, Any]:
        return await self._inventory_rpc(
            "inventory_reconcile_stock",
            {"p_product_id": product_id, "p_counted_stock": counted_stock,
             "p_reason": reason, "p_metadata": metadata},
        )

    async def list_inventory_history(self, product_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await (
            admin_sb.table("inventory_activity")
            .select("id, product_id, sku, activity_type, delta, stock_after, reference_type, reference_id, reason, metadata, created_at")
            .eq("product_id", product_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return getattr(res, "data", None) or []

    async def get_inventory_summary(self, low_stock_only: bool = False) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await (
            admin_sb.table("products")
            .select("id, name, sku, stock, low_stock_threshold, is_active")
            .eq("is_active", True)
            .order("stock")
            .execute()
        )
        data = getattr(res, "data", None) or []
        if low_stock_only:
            data = [item for item in data if item.get("stock", 0) <= item.get("low_stock_threshold", 10)]
        return data

    async def _inventory_rpc(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(name, params).execute()
            data = getattr(res, "data", None)
            if isinstance(data, list):
                data = data[0] if data else None
            if not data:
                raise RuntimeError(f"{name} returned no data.")
            return data
        except Exception as exc:
            logger.error("Inventory RPC %s failed: %s", name, exc, exc_info=True)
            raise

    async def create_pending_order_with_reservation(self, order_data: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.rpc("create_pending_order_with_reservation", {"p_order_data": order_data, "p_items": items}).execute()
        data = getattr(res, "data", None)
        if not data:
            raise RuntimeError("RPC returned no data for pending order reservation.")
        return data

    async def settle_order_transaction(
        self, order_id: str, pi_id: str, amount: float, user_id: str,
        payment_method: Optional[str] = None, stripe_currency: Optional[str] = None,
    ) -> str:
        if not stripe_currency:
            raise ValueError("Verified payment currency is required for payment settlement")
        provider = get_current_provider_key()
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.rpc(
            "settle_payment_transaction",
            {"p_order_id": order_id, "p_provider": provider, "p_provider_payment_id": pi_id,
             "p_amount": amount, "p_user_id": user_id, "p_payment_method": payment_method,
             "p_currency": stripe_currency},
        ).execute()
        data = getattr(res, "data", None)
        return str(data) if data else "FAILED"

    async def release_abandoned_order(self, order_id: str, reason: str = "order_cancelled") -> str:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.rpc("cancel_order_and_release_stock", {"p_order_id": order_id, "p_reason": reason}).execute()
        data = getattr(res, "data", None)
        return str(data) if data else "FAILED"

    async def cancel_order_and_restore_stock(self, order_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("orders").select("*").eq("id", order_id).maybe_single().execute()
        order = getattr(res, "data", None)
        if not order or order.get("status") not in ("pending", "paid", "processing"):
            return None
        reason = "customer_requested" if user_id else "admin_requested"
        rpc_res = await admin_sb.rpc("cancel_order_and_release_stock", {"p_order_id": order_id, "p_reason": reason}).execute()
        rpc_result = str(getattr(rpc_res, "data", "FAILED"))
        if rpc_result in ("CANCELLED", "ALREADY_CANCELLED"):
            updated = await admin_sb.table("orders").select("*").eq("id", order_id).maybe_single().execute()
            return getattr(updated, "data", None)
        return None

    async def get_low_stock_products(self) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("products").select("id, name, stock, low_stock_threshold, is_active").eq("is_active", True).execute()
        data = getattr(res, "data", None) or []
        return [item for item in data if item.get("stock", 0) <= item.get("low_stock_threshold", 10)]

    async def list_stale_pending_orders(self, minutes_old: int = 30) -> List[Dict[str, Any]]:
        if minutes_old <= 0:
            raise ValueError("minutes_old must be positive")
        admin_sb = await get_async_admin_supabase()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
        # Abandoned-order cleanup is for provider-backed checkouts only.
        # COD/offline pending orders must never enter the online-payment sweeper.
        res = await (
            admin_sb.table("orders")
            .select("id, created_at, customer_id, payment_provider, provider_payment_id, stripe_payment_intent")
            .eq("status", "pending")
            .lt("created_at", cutoff.isoformat())
            .or_("provider_payment_id.not.is.null,stripe_payment_intent.not.is.null")
            .execute()
        )
        return getattr(res, "data", None) or []
