"""
Payment Repository
==================
Path: app/repositories/payment_repo.py
"""
import logging
from typing import Any
from .base import BaseRepository

logger = logging.getLogger(__name__)

class PaymentRepository(BaseRepository):
    
    def get_order_for_payment(self, order_id: str, user_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("orders").select("id, status, total_amount, stripe_payment_intent, customer_id").eq("id", order_id).eq("customer_id", user_id).maybe_single().execute()
        return res.data if res and hasattr(res, "data") else None

    def update_order_pi(self, order_id: str, pi_id: str) -> None:
        self.admin_sb.table("orders").update({"stripe_payment_intent": pi_id}).eq("id", order_id).execute()

    def update_order_status(self, order_id: str, new_status: str, expected_status: str) -> bool:
        res = self.admin_sb.table("orders").update({"status": new_status}).eq("id", order_id).eq("status", expected_status).execute()
        return bool(res and hasattr(res, "data") and res.data)

    def create_payment_record(self, order_id: str, pi_id: str, amount: float, currency: str, status: str, method: str) -> None:
        try:
            self.admin_sb.table("payments").insert({
                "order_id": order_id, "stripe_payment_intent_id": pi_id,
                "amount": amount, "currency": currency, "status": status, "payment_method": method
            }).execute()
        except Exception as e:
            logger.warning("Failed to insert payment record: %s", e)

    def get_order_by_pi(self, pi_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("orders").select("id, status, total_amount, customer_id, order_items(*)").eq("stripe_payment_intent", pi_id).maybe_single().execute()
        return res.data if res and hasattr(res, "data") else None

    def get_customer_email(self, customer_id: str) -> str:
        if not customer_id: return ""
        try:
            res = self.admin_sb.table("users").select("email").eq("id", customer_id).limit(1).execute()
            return res.data[0].get("email", "") if res and hasattr(res, "data") and res.data else ""
        except Exception:
            return ""