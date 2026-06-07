"""
Admin Repository
================
Path: app/repositories/admin_repo.py
"""
import logging
from typing import Dict, Any
from .base import BaseRepository

logger = logging.getLogger(__name__)

class AdminRepository(BaseRepository):
    def get_live_admin_profile(self, user_id: str) -> dict[str, Any] | None:
        """Bypasses cache to do a live check of admin privileges."""
        try:
            res = (
                self.admin_sb.table("users")
                .select("id, email, full_name, role, is_active, created_at")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            return res.data[0] if res and hasattr(res, "data") and res.data else None
        except Exception as e:
            logger.error("Admin DB error | user=%s: %s", user_id[:8], e)
            return None

    def get_dashboard_stats(self) -> Dict[str, float | int]:
        """Aggregates metrics for the admin dashboard. Safe fallbacks for errors."""
        stats = {"products": -1, "orders": -1, "pending_orders": -1, "users": -1, "revenue": -1}

        try:
            prods = self.admin_sb.table("products").select("id", count="exact").eq("is_active", True).limit(1).execute()
            stats["products"] = prods.count if prods and hasattr(prods, "count") else 0
        except Exception: pass

        try:
            orders = self.admin_sb.table("orders").select("id", count="exact").limit(1).execute()
            stats["orders"] = orders.count if orders and hasattr(orders, "count") else 0
        except Exception: pass

        try:
            users = self.admin_sb.table("users").select("id", count="exact").limit(1).execute()
            stats["users"] = users.count if users and hasattr(users, "count") else 0
        except Exception: pass

        try:
            rev_res = self.admin_sb.table("orders").select("total_amount").in_("status", ["paid", "shipped", "delivered"]).execute()
            if rev_res and hasattr(rev_res, "data") and rev_res.data:
                stats["revenue"] = round(sum(float(o.get("total_amount", 0)) for o in rev_res.data), 2)
            else:
                stats["revenue"] = 0
        except Exception: pass

        return stats