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
            raise RuntimeError("Unable to verify administrator profile") from exc

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Fetch independent dashboard counters concurrently.

        This method intentionally fails closed. A database error must never be
        rendered as a legitimate zero in the admin console.
        """
        stats: Dict[str, Any] = {}

        async def fetch_products() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("products").select("id", count="exact").eq("is_active", True).limit(1).execute()
            stats["products"] = res.count or 0

        async def fetch_orders() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("orders").select("id", count="exact").limit(1).execute()
            stats["orders"] = res.count or 0

        async def fetch_pending() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("orders").select("id", count="exact").eq("status", "pending").limit(1).execute()
            stats["pending_orders"] = res.count or 0

        async def fetch_users() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("users").select("id", count="exact").limit(1).execute()
            stats["users"] = res.count or 0

        async def fetch_revenue() -> None:
            sb = await get_async_admin_supabase()
            res = await sb.table("orders").select("total_amount").in_("status", ["paid", "shipped", "delivered"]).execute()
            data = getattr(res, "data", None) or []
            stats["revenue"] = round(sum(float(order.get("total_amount") or 0) for order in data), 2)

        results = await asyncio.gather(
            fetch_products(),
            fetch_orders(),
            fetch_pending(),
            fetch_users(),
            fetch_revenue(),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, Exception)]
        if failures:
            for failure in failures:
                logger.error("Admin dashboard query failed: %s", failure, exc_info=failure)
            raise RuntimeError("Unable to load complete dashboard telemetry") from failures[0]

        return stats
