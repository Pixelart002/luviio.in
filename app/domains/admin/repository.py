"""Admin domain repository — async Supabase persistence."""
import asyncio
import logging
from typing import Any, Dict, Optional

from app.core.supabase import get_async_admin_supabase
from app.utils.timestamp import ts_to_iso

logger = logging.getLogger(__name__)


class AsyncAdminRepository:
    """Persistence boundary for administrator and dashboard data."""

    async def get_live_admin_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the live administrator profile without frontend cache dependencies."""
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
            logger.error(
                "DB error fetching admin profile | user=%.8s: %s",
                user_id,
                exc,
                exc_info=True,
            )
            return None

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Fetch independent dashboard counters concurrently."""
        stats = {
            "products": 0,
            "orders": 0,
            "pending_orders": 0,
            "users": 0,
            "revenue": 0.0,
        }

        async def fetch_products() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("products").select(
                    "id", count="exact"
                ).eq("is_active", True).limit(1).execute()
                stats["products"] = res.count or 0
            except Exception as exc:
                logger.error("Stats product query failed: %s", exc, exc_info=True)

        async def fetch_orders() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("orders").select(
                    "id", count="exact"
                ).limit(1).execute()
                stats["orders"] = res.count or 0
            except Exception as exc:
                logger.error("Stats order query failed: %s", exc, exc_info=True)

        async def fetch_pending() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("orders").select(
                    "id", count="exact"
                ).eq("status", "pending").limit(1).execute()
                stats["pending_orders"] = res.count or 0
            except Exception as exc:
                logger.error("Stats pending-order query failed: %s", exc, exc_info=True)

        async def fetch_users() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("users").select(
                    "id", count="exact"
                ).limit(1).execute()
                stats["users"] = res.count or 0
            except Exception as exc:
                logger.error("Stats user query failed: %s", exc, exc_info=True)

        async def fetch_revenue() -> None:
            try:
                sb = await get_async_admin_supabase()
                res = await sb.table("orders").select(
                    "total_amount"
                ).in_("status", ["paid", "shipped", "delivered"]).execute()
                data = getattr(res, "data", None) or []
                stats["revenue"] = round(
                    sum(float(order.get("total_amount") or 0) for order in data),
                    2,
                )
            except Exception as exc:
                logger.error("Stats revenue query failed: %s", exc, exc_info=True)

        await asyncio.gather(
            fetch_products(),
            fetch_orders(),
            fetch_pending(),
            fetch_users(),
            fetch_revenue(),
            return_exceptions=True,
        )
        return stats
