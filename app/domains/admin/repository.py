"""Admin domain repository — async Supabase persistence."""
import asyncio
import logging
from typing import Any, Dict, Optional

from app.core.supabase import get_async_admin_supabase
from app.utils.timestamp import ts_to_iso

logger = logging.getLogger(__name__)


class AsyncAdminRepository:
    """Persistence boundary for administrator, reporting and audit data."""

    async def get_live_admin_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("users").select("id, email, full_name, role, is_active, created_at").eq("id", user_id).limit(1).execute()
        data = getattr(res, "data", None)
        if data:
            profile = data[0]
            profile["created_at"] = ts_to_iso(profile.get("created_at"))
            return profile
        return None

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        async def products():
            sb = await get_async_admin_supabase(); r = await sb.table("products").select("id", count="exact").eq("is_active", True).limit(1).execute(); stats["products"] = r.count or 0
        async def orders():
            sb = await get_async_admin_supabase(); r = await sb.table("orders").select("id", count="exact").limit(1).execute(); stats["orders"] = r.count or 0
        async def pending():
            sb = await get_async_admin_supabase(); r = await sb.table("orders").select("id", count="exact").eq("status", "pending").limit(1).execute(); stats["pending_orders"] = r.count or 0
        async def users():
            sb = await get_async_admin_supabase(); r = await sb.table("users").select("id", count="exact").limit(1).execute(); stats["users"] = r.count or 0
        async def revenue():
            sb = await get_async_admin_supabase(); r = await sb.table("orders").select("total_amount").in_("status", ["paid", "shipped", "delivered"]).execute(); stats["revenue"] = round(sum(float(x.get("total_amount") or 0) for x in (getattr(r, "data", None) or [])), 2)
        results = await asyncio.gather(products(), orders(), pending(), users(), revenue(), return_exceptions=True)
        failures = [x for x in results if isinstance(x, Exception)]
        if failures: raise RuntimeError("Unable to load complete dashboard telemetry") from failures[0]
        return stats

    async def get_report_summary(self) -> Dict[str, Any]:
        sb = await get_async_admin_supabase()
        orders = getattr((await sb.table("orders").select("id,status,total_amount,created_at").order("created_at", desc=True).limit(1000).execute()), "data", None) or []
        products = getattr((await sb.table("products").select("id,name,stock,low_stock_threshold,is_active").limit(500).execute()), "data", None) or []
        items = getattr((await sb.table("order_items").select("product_id,product_name,quantity,subtotal").limit(5000).execute()), "data", None) or []
        status_counts: Dict[str, int] = {}
        revenue = 0.0
        for order in orders:
            status_counts[order.get("status", "unknown")] = status_counts.get(order.get("status", "unknown"), 0) + 1
            if order.get("status") in {"paid", "processing", "shipped", "delivered"}: revenue += float(order.get("total_amount") or 0)
        top: Dict[str, Dict[str, Any]] = {}
        for item in items:
            key = str(item.get("product_id") or item.get("product_name") or "unknown")
            row = top.setdefault(key, {"product_id": item.get("product_id"), "product_name": item.get("product_name") or "Product", "quantity": 0, "sales": 0.0})
            row["quantity"] += int(item.get("quantity") or 0); row["sales"] += float(item.get("subtotal") or 0)
        top_products = sorted(top.values(), key=lambda x: (x["quantity"], x["sales"]), reverse=True)[:10]
        low_stock = sum(1 for p in products if p.get("is_active") and int(p.get("stock") or 0) <= int(p.get("low_stock_threshold") or 0))
        return {"orders": len(orders), "revenue": round(revenue, 2), "status_counts": status_counts, "top_products": top_products, "low_stock_products": low_stock, "generated_at": ts_to_iso(__import__('time').time())}

    async def get_payment_report(self) -> list[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        r = await sb.table("payments").select("id,order_id,amount,amount_paise,currency,status,payment_method,error_code,error_message,attempt_number,total_attempts,latest_payment_intent_id,created_at,updated_at,orders(order_number,status,total_amount)").order("created_at", desc=True).limit(200).execute()
        return getattr(r, "data", None) or []

    async def get_audit_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        r = await sb.table("audit_logs").select("id,request_id,actor_user_id,method,path,status_code,duration_ms,created_at").order("created_at", desc=True).limit(limit).execute()
        return getattr(r, "data", None) or []
