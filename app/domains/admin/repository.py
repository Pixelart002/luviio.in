"""Admin domain repository — async Supabase persistence."""
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from app.core.supabase import get_async_admin_supabase
from app.utils.timestamp import ts_to_iso

logger = logging.getLogger(__name__)


class AsyncAdminRepository:
    """Persistence boundary for administrator, reporting and audit data."""

    async def get_live_admin_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await (
            admin_sb.table("users")
            .select("id, email, full_name, role, is_active, created_at")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        data = getattr(res, "data", None)
        if not data:
            return None
        profile = data[0]
        profile["created_at"] = ts_to_iso(profile.get("created_at"))
        return profile

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}

        async def products() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("products").select("id", count="exact").eq("is_active", True).limit(1).execute()
            stats["products"] = res.count or 0

        async def orders() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("orders").select("id", count="exact").limit(1).execute()
            stats["orders"] = res.count or 0

        async def pending() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("orders").select("id", count="exact").eq("status", "pending").limit(1).execute()
            stats["pending_orders"] = res.count or 0

        async def users() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("users").select("id", count="exact").limit(1).execute()
            stats["users"] = res.count or 0

        async def revenue() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("orders").select("total_amount").in_("status", ["paid", "shipped", "delivered"]).execute()
            stats["revenue"] = round(sum(float(row.get("total_amount") or 0) for row in (getattr(res, "data", None) or [])), 2)

        results = await asyncio.gather(products(), orders(), pending(), users(), revenue(), return_exceptions=True)
        failures = [result for result in results if isinstance(result, Exception)]
        if failures:
            raise RuntimeError("Unable to load complete dashboard telemetry") from failures[0]
        return stats

    async def get_report_summary(self) -> Dict[str, Any]:
        sb = await get_async_admin_supabase()
        orders_res = await sb.table("orders").select("id,status,total_amount,created_at,payment_method").order("created_at", desc=True).limit(1000).execute()
        products_res = await sb.table("products").select("id,name,stock,low_stock_threshold,is_active").limit(500).execute()
        items_res = await sb.table("order_items").select("product_id,product_name,quantity,subtotal").limit(5000).execute()
        orders = getattr(orders_res, "data", None) or []
        products = getattr(products_res, "data", None) or []
        items = getattr(items_res, "data", None) or []

        status_counts: Dict[str, int] = {}
        revenue = 0.0
        for order in orders:
            state = order.get("status", "unknown")
            status_counts[state] = status_counts.get(state, 0) + 1
            if state in {"paid", "processing", "shipped", "delivered"}:
                revenue += float(order.get("total_amount") or 0)

        top: Dict[str, Dict[str, Any]] = {}
        for item in items:
            key = str(item.get("product_id") or item.get("product_name") or "unknown")
            row = top.setdefault(key, {"product_id": item.get("product_id"), "product_name": item.get("product_name") or "Product", "quantity": 0, "sales": 0.0})
            row["quantity"] += int(item.get("quantity") or 0)
            row["sales"] += float(item.get("subtotal") or 0)

        low_stock = sum(1 for product in products if product.get("is_active") and int(product.get("stock") or 0) <= int(product.get("low_stock_threshold") or 0))
        return {"orders": len(orders), "revenue": round(revenue, 2), "status_counts": status_counts, "top_products": sorted(top.values(), key=lambda row: (row["quantity"], row["sales"]), reverse=True)[:10], "low_stock_products": low_stock, "generated_at": ts_to_iso(time.time())}

    async def get_payment_report(self, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        sb = await get_async_admin_supabase()
        res = await sb.rpc("admin_payment_telemetry", {"p_limit": limit, "p_offset": offset}).execute()
        data = getattr(res, "data", None) or []
        total_count = int(data[0].get("total_count") or 0) if data else 0
        items = [{key: value for key, value in row.items() if key != "total_count"} for row in data]
        return {"items": items, "has_more": offset + len(items) < total_count, "next_offset": offset + len(items), "total_count": total_count}

    async def get_audit_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        res = await (
            sb.table("audit_logs")
            .select("id,request_id,actor_user_id,method,path,status_code,duration_ms,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return getattr(res, "data", None) or []
