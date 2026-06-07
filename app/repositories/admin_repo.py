"""
Admin Repository
================
Path: app/repositories/admin_repo.py
"""
import logging
from typing import Any, Dict, Optional
from .base import BaseRepository

logger = logging.getLogger(__name__)

class AdminRepository(BaseRepository):
    
    def get_live_admin_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch live user profile bypassing frontend cache."""
        try:
            res = (
                self.admin_sb.table("users")
                .select("id, email, full_name, role, is_active, created_at")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            return res.data[0] if res and getattr(res, "data", None) else None
        except Exception as exc:
            logger.error("DB error fetching admin profile | user=%.8s: %s", user_id, exc)
            return None

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Aggregate stats for the admin dashboard."""
        stats = {
            "products": 0,
            "orders": 0,
            "pending_orders": 0,
            "users": 0,
            "revenue": 0.0
        }
        
        # Products Count
        try:
            prod_res = self.admin_sb.table("products").select("id", count="exact").eq("is_active", True).limit(1).execute()
            stats["products"] = prod_res.count if prod_res and hasattr(prod_res, "count") and prod_res.count else 0
        except Exception as exc:
            logger.warning("Stats: product count failed: %s", exc)

        # Total Orders Count
        try:
            ord_res = self.admin_sb.table("orders").select("id", count="exact").limit(1).execute()
            stats["orders"] = ord_res.count if ord_res and hasattr(ord_res, "count") and ord_res.count else 0
        except Exception as exc:
            logger.warning("Stats: order count failed: %s", exc)

        # Pending Orders Count
        try:
            pend_res = self.admin_sb.table("orders").select("id", count="exact").eq("status", "pending").limit(1).execute()
            stats["pending_orders"] = pend_res.count if pend_res and hasattr(pend_res, "count") and pend_res.count else 0
        except Exception as exc:
            logger.warning("Stats: pending count failed: %s", exc)

        # Users Count
        try:
            usr_res = self.admin_sb.table("users").select("id", count="exact").limit(1).execute()
            stats["users"] = usr_res.count if usr_res and hasattr(usr_res, "count") and usr_res.count else 0
        except Exception as exc:
            logger.warning("Stats: user count failed: %s", exc)

        # Revenue Calculation (Paid + Shipped + Delivered)
        try:
            rev_res = self.admin_sb.table("orders").select("total_amount").in_("status", ["paid", "shipped", "delivered"]).execute()
            if rev_res and hasattr(rev_res, "data") and rev_res.data:
                stats["revenue"] = round(sum(float(o.get("total_amount", 0)) for o in rev_res.data), 2)
        except Exception as exc:
            logger.warning("Stats: revenue calc failed: %s", exc)

        return stats