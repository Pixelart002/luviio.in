"""
Admin Repository — Async Enterprise Grade
=========================================
Path: app/repositories/admin_repo.py

Architecture & Fixes:
  ✅ Stateless Execution — Fetches Supabase Admin client on-demand inside async methods.
  ✅ Resolves Coroutine Crash — Awaits async client factory to prevent AttributeError.
"""
import logging
import asyncio
from typing import Any, Dict, Optional
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncAdminRepository:
    def __init__(self):
        # Deferred client initialization to prevent coroutine AttributeError in sync constructor
        pass
    
    async def get_live_admin_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch live user profile bypassing frontend cache."""
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select("id, email, full_name, role, is_active, created_at").eq("id", user_id).limit(1).execute()
            return res.data[0] if res and getattr(res, "data", None) else None
        except Exception as exc:
            logger.error("DB error fetching admin profile | user=%.8s: %s", user_id, exc)
            return None

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Aggregate stats for the admin dashboard concurrently for massive speedup."""
        admin_sb = await get_async_admin_supabase()
        stats = {"products": 0, "orders": 0, "pending_orders": 0, "users": 0, "revenue": 0.0}

        # Define individual async tasks
        async def fetch_products():
            try:
                res = await admin_sb.table("products").select("id", count="exact").eq("is_active", True).limit(1).execute()
                stats["products"] = res.count or 0
            except Exception as e: logger.warning("Stats product err: %s", e)

        async def fetch_orders():
            try:
                res = await admin_sb.table("orders").select("id", count="exact").limit(1).execute()
                stats["orders"] = res.count or 0
            except Exception as e: logger.warning("Stats order err: %s", e)

        async def fetch_pending():
            try:
                res = await admin_sb.table("orders").select("id", count="exact").eq("status", "pending").limit(1).execute()
                stats["pending_orders"] = res.count or 0
            except Exception as e: logger.warning("Stats pending err: %s", e)

        async def fetch_users():
            try:
                res = await admin_sb.table("users").select("id", count="exact").limit(1).execute()
                stats["users"] = res.count or 0
            except Exception as e: logger.warning("Stats users err: %s", e)

        async def fetch_revenue():
            try:
                res = await admin_sb.table("orders").select("total_amount").in_("status", ["paid", "shipped", "delivered"]).execute()
                if res and res.data:
                    stats["revenue"] = round(sum(float(o.get("total_amount", 0)) for o in res.data), 2)
            except Exception as e: logger.warning("Stats revenue err: %s", e)

        # 🔥 Run all 5 DB queries in parallel
        await asyncio.gather(
            fetch_products(), fetch_orders(), fetch_pending(), fetch_users(), fetch_revenue()
        )

        return stats