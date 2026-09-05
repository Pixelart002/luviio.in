"""
Admin Repository — Async Enterprise Grade
=========================================
Path: app/repositories/admin_repo.py
"""
import logging
import asyncio
from typing import Any, Dict, Optional
from app.core.supabase import get_async_admin_supabase
from app.utils.timestamp import ts_to_iso

logger = logging.getLogger(__name__)

class AsyncAdminRepository:
    def __init__(self) -> None:
        pass
    
    async def get_live_admin_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch live user profile bypassing frontend cache."""
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select(
                "id, email, full_name, role, is_active, created_at"
            ).eq("id", user_id).limit(1).execute()
            
            data = getattr(res, "data", None)
            if data:
                profile = data[0]
                profile["created_at"] = ts_to_iso(profile.get("created_at"))
                return profile
            return None
        except Exception as exc:
            logger.error("DB error fetching admin profile | user=%.8s: %s", user_id, exc, exc_info=True)
            return None

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Aggregate stats for the admin dashboard concurrently for massive speedup."""
        stats = {"products": 0, "orders": 0, "pending_orders": 0, "users": 0, "revenue": 0.0}

        async def fetch_products() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("products").select("id", count="exact").eq("is_active", True).limit(1).execute()
                stats["products"] = res.count or 0
            except Exception as e: 
                logger.error("Stats product err: %s", e, exc_info=True)

        async def fetch_orders() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("orders").select("id", count="exact").limit(1).execute()
                stats["orders"] = res.count or 0
            except Exception as e: 
                logger.error("Stats order err: %s", e, exc_info=True)

        async def fetch_pending() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("orders").select("id", count="exact").eq("status", "pending").limit(1).execute()
                stats["pending_orders"] = res.count or 0
            except Exception as e: 
                logger.error("Stats pending err: %s", e, exc_info=True)

        async def fetch_users() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("users").select("id", count="exact").limit(1).execute()
                stats["users"] = res.count or 0
            except Exception as e: 
                logger.error("Stats users err: %s", e, exc_info=True)

        async def fetch_revenue() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("orders").select("total_amount").in_("status", ["paid", "shipped", "delivered"]).execute()
                data = getattr(res, "data", None)
                if data:
                    stats["revenue"] = round(sum(float(o.get("total_amount", 0)) for o in data), 2)
            except Exception as e: 
                logger.error("Stats revenue err: %s", e, exc_info=True)

        await asyncio.gather(
            fetch_products(), fetch_orders(), fetch_pending(), fetch_users(), fetch_revenue(),
            return_exceptions=True
        )

        return stats