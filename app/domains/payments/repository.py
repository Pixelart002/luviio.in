"""
Payments Repository -- ACID & JIT Hybrid Flow (Enterprise Grade & GST Ready)
============================================================================
Canonical payment persistence boundary. Critical checkout, pricing, retry-limit
and webhook-ledger reads fail closed: database failures must never be treated as
"nothing exists" or "safe to continue".
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.supabase import get_async_admin_supabase
from app.integrations.payments.context import get_current_provider_key

logger = logging.getLogger(__name__)


class AsyncPaymentRepository:
    async def has_active_pending_order(self, user_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        try:
            res = (
                await admin_sb.table("orders")
                .select("id")
                .eq("customer_id", user_id)
                .eq("status", "pending")
                .limit(1)
                .execute()
            )
            return bool(getattr(res, "data", None))
        except Exception as exc:
            logger.error("DB Error checking active pending order for user %s: %s", user_id, exc, exc_info=True)
            raise RuntimeError("Unable to verify active pending orders") from exc

    async def get_cart_items_for_checkout(self, user_id: str) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await (
                admin_sb.table("carts")
                .select(
                    "id, cart_items(id, product_id, quantity, price_snapshot, "
                    "products(name, price, compare_price, stock, hsn_code, gst_percentage, is_active))"
                )
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            data = getattr(res, "data", None)
            return data.get("cart_items", []) if data else []
        except Exception as exc:
            logger.error("DB Error fetching cart items for user %s: %s", user_id, exc, exc_info=True)
            raise RuntimeError("Unable to load checkout cart") from exc

    async def get_shipping_address(self, address_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        if address_id == "dummy":
            return {"line1": "123 Demo St", "city": "Demo", "postal_code": "000000", "country": "IN"}
        admin_sb = await get_async_admin_supabase()
        try:
            res = await (
                admin_sb.table("addresses")
                .select("*")
                .eq("id", address_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching address %s: %s", address_id, exc, exc_info=True)
            raise RuntimeError("Unable to load checkout address") from exc

    async def get_pricing_config(self) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc("get_canonical_pricing_config").execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("Canonical pricing configuration is missing")
            return data
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("DB Error fetching canonical pricing config: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load pricing configuration") from exc

    async def get_customer_email(self, user_id: str) -> str:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
            data = getattr(res, "data", None)
            if not data or not data.get("email"):
                raise RuntimeError("Customer email is missing")
            return data["email"]
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("DB Error fetching email for user %s: %s", user_id, exc, exc_info=True)
            raise RuntimeError("Unable to load customer email") from exc

    async def get_order_by_idempotency_key(self, user_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        try:
            res = await (
                admin_sb.table("orders")
                .select("*")
                .eq("customer_id", user_id)
                .eq("idempotency_key", idempotency_key)
                .maybe_single()
                .execute()
            )
            data = getattr(res, "data", None)
            provider_payment_id = data.get("provider_payment_id") if data else None
            if provider_payment_id:
                # Compatibility alias for existing orchestration code. It is
                # internal-only and is never serialized into public responses.
                stored_provider = str(data.get("payment_provider") or provider).strip().lower()
                if stored_provider == provider:
                    data.setdefault("stripe_payment_intent", provider_payment_id)
            return data
        except Exception as exc:
            logger.error("DB Error checking idempotency key %s: %s", idempotency_key, exc, exc_info=True)
            raise RuntimeError("Unable to verify idempotency key") from exc

    async def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await (
                admin_sb.table("orders")
                .select("*, order_items(*, products(name, compare_price, hsn_code, gst_percentage))")
                .eq("id", order_id)
                .maybe_single()
                .execute()
            )
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching order %s: %s", order_id, exc, exc_info=True)
            raise RuntimeError("Unable to load order") from exc

    async def create_checkout_payment_attempt(
        self, customer_id: str, idempotency_key: str, amount_paise: int, currency: str = "inr"
    ) -> str:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        try:
            res = await admin_sb.rpc(
                "create_checkout_payment_attempt",
                {
                    "p_customer_id": customer_id,
                    "p_idempotency_key": idempotency_key,
                    "p_provider": provider,
                    "p_amount_paise": amount_paise,
                    "p_currency": currency,
                },
            ).execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("Checkout payment attempt RPC returned no id")
            row = data[0] if isinstance(data, list) else data
            return str(row.get("id") if isinstance(row, dict) else row)
        except Exception as exc:
            logger.error("DB Error creating checkout payment attempt: %s", exc, exc_info=True)
            raise RuntimeError("Unable to create durable checkout payment attempt") from exc

    async def update_checkout_payment_attempt(
        self, attempt_id: str, provider_payment_id: Optional[str] = None,
        status: Optional[str] = None, last_error: Optional[str] = None
    ) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc(
                "update_checkout_payment_attempt",
                {
                    "p_id": attempt_id,
                    "p_provider_payment_id": provider_payment_id,
                    "p_status": status,
                    "p_last_error": last_error,
                },
            ).execute()
        except Exception as exc:
            logger.error("DB Error updating checkout payment attempt %s: %s", attempt_id, exc, exc_info=True)
            raise RuntimeError("Unable to update durable checkout payment attempt") from exc

    async def list_stale_checkout_payment_attempts(self, cutoff_iso: str) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await (
                admin_sb.table("checkout_payment_attempts")
                .select("id, customer_id, idempotency_key, payment_provider, provider_payment_id, amount_paise, currency, status, created_at, expires_at")
                .lt("expires_at", cutoff_iso)
                .in_("status", ["provider_pending", "provider_created", "cancel_requested", "orphan_risk"])
                .order("expires_at")
                .limit(100)
                .execute()
            )
            return getattr(res, "data", None) or []
        except Exception as exc:
            logger.error("DB Error listing stale checkout payment attempts: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load stale checkout payment attempts") from exc

    async def create_pending_order_with_reservation(
        self, order_data: Dict[str, Any], items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        provider_payment_id = str(
            order_data.get("provider_payment_id") or order_data.get("stripe_payment_intent") or ""
        ).strip()
        if not provider_payment_id:
            raise RuntimeError("Provider payment reference is required before order creation.")

        payload = dict(order_data)
        payload["payment_provider"] = provider
        payload["provider_payment_id"] = provider_payment_id
        if provider != "stripe":
            payload.pop("stripe_payment_intent", None)

        try:
            res = await admin_sb.rpc(
                "create_pending_order_with_payment",
                {"p_order_data": payload, "p_items": items},
            ).execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("RPC returned no data for pending order reservation.")
            return data
        except Exception as exc:
            logger.error("RPC Error reserving stock and creating order: %s", exc, exc_info=True)
            raise

    async def settle_order_transaction(
        self,
        order_id: str,
        pi_id: str,
        amount: float,
        user_id: str,
        payment_method: Optional[str] = None,
        stripe_currency: Optional[str] = None,
    ) -> str:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        if stripe_currency is None:
            raise RuntimeError("Payment currency is required for provider-neutral settlement")

        res = await admin_sb.rpc(
            "settle_payment_transaction",
            {
                "p_order_id": order_id,
                "p_provider": provider,
                "p_provider_payment_id": pi_id,
                "p_amount": amount,
                "p_user_id": user_id,
                "p_payment_method": payment_method,
                "p_currency": stripe_currency,
            },
        ).execute()
        data = getattr(res, "data", None)
        return str(data) if data else "FAILED"

    async def create_refund_attempt(
        self,
        order_id: str,
        provider: str,
        provider_payment_id: str,
        amount: float,
        currency: str,
        idempotency_key: str,
        reason: Optional[str] = None,
        reference: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "create_payment_refund_attempt",
                {
                    "p_order_id": order_id,
                    "p_provider": provider,
                    "p_provider_payment_id": provider_payment_id,
                    "p_amount": amount,
                    "p_currency": currency,
                    "p_idempotency_key": idempotency_key,
                    "p_reason": reason,
                    "p_reference": reference,
                    "p_metadata": metadata or {},
                },
            ).execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("Refund-attempt RPC returned no data")
            return data
        except Exception as exc:
            logger.error("DB Error creating refund attempt for order %s: %s", order_id, exc, exc_info=True)
            raise RuntimeError("Unable to create refund attempt") from exc

    async def complete_refund_attempt(
        self,
        refund_attempt_id: str,
        status: str,
        provider_refund_id: Optional[str] = None,
        failure_code: Optional[str] = None,
        failure_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "complete_payment_refund_attempt",
                {
                    "p_refund_id": refund_attempt_id,
                    "p_status": status,
                    "p_provider_refund_id": provider_refund_id,
                    "p_failure_code": failure_code,
                    "p_failure_message": failure_message,
                    "p_metadata": metadata or {},
                },
            ).execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("Refund-attempt completion RPC returned no data")
            return data
        except Exception as exc:
            logger.error("DB Error completing refund attempt %s: %s", refund_attempt_id, exc, exc_info=True)
            raise RuntimeError("Unable to complete refund attempt") from exc

    async def record_refund_accounting(
        self,
        order_id: str,
        provider: str,
        provider_payment_id: str,
        amount: float,
        currency: str = "INR",
        reference: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist provider refund state and an idempotent refund ledger entry."""
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "record_payment_refund",
                {
                    "p_order_id": order_id,
                    "p_provider": provider,
                    "p_provider_payment_id": provider_payment_id,
                    "p_amount": amount,
                    "p_currency": currency,
                    "p_reference": reference,
                    "p_metadata": metadata or {},
                },
            ).execute()
            data = getattr(res, "data", None)
            result = str(data) if data is not None else "FAILED"
            if result != "REFUNDED_ACCOUNTED":
                raise RuntimeError(f"Refund accounting RPC returned {result}")
            return result
        except Exception as exc:
            logger.error(
                "DB Error recording refund accounting for order %s: %s",
                order_id,
                exc,
                exc_info=True,
            )
            raise RuntimeError("Unable to persist refund accounting") from exc

    async def update_order_payment_intent(self, order_id: str, new_pi_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        values: Dict[str, Any] = {"payment_provider": provider, "provider_payment_id": new_pi_id}
        if provider == "stripe":
            values["stripe_payment_intent"] = new_pi_id
        try:
            res = await (
                admin_sb.table("orders")
                .update(values)
                .eq("id", order_id)
                .eq("status", "pending")
                .execute()
            )
            return bool(getattr(res, "data", None))
        except Exception as exc:
            logger.error("DB Error updating payment reference for order %s: %s", order_id, exc, exc_info=True)
            raise

    async def clear_order_payment_intent(self, order_id: str, expected_pi_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        values: Dict[str, Any] = {"provider_payment_id": None}
        if provider == "stripe":
            values["stripe_payment_intent"] = None
        try:
            res = await (
                admin_sb.table("orders")
                .update(values)
                .eq("id", order_id)
                .eq("status", "pending")
                .eq("payment_provider", provider)
                .eq("provider_payment_id", expected_pi_id)
                .execute()
            )
            return bool(getattr(res, "data", None))
        except Exception as exc:
            logger.error("DB Error clearing payment reference for order %s: %s", order_id, exc, exc_info=True)
            raise

    async def record_payment_attempt(
        self,
        order_id: str,
        user_id: Optional[str],
        pi_id: str,
        amount: float,
        status: str,
        payment_method: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        try:
            await admin_sb.rpc(
                "record_payment_attempt_provider",
                {
                    "p_order_id": order_id,
                    "p_user_id": user_id,
                    "p_provider": provider,
                    "p_provider_payment_id": pi_id,
                    "p_amount": amount,
                    "p_status": status,
                    "p_payment_method": payment_method,
                    "p_error_code": error_code,
                    "p_error_message": error_message,
                    "p_ip_address": ip_address,
                    "p_user_agent": user_agent,
                },
            ).execute()
        except Exception as exc:
            logger.error("RPC Error recording payment attempt for %s/%s: %s", provider, pi_id, exc, exc_info=True)
            raise RuntimeError("Unable to record payment attempt") from exc

    async def get_attempt_count(self, order_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("payments").select("total_attempts").eq("order_id", order_id).maybe_single().execute()
            data = getattr(res, "data", None)
            if not data or data.get("total_attempts") is None:
                raise RuntimeError("Payment attempt counter is missing")
            return int(data["total_attempts"])
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("DB Error reading attempt count for order %s: %s", order_id, exc, exc_info=True)
            raise RuntimeError("Unable to verify payment attempt limit") from exc

    async def get_order_by_payment_intent(self, pi_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        try:
            res = await (
                admin_sb.table("orders")
                .select("*")
                .eq("payment_provider", provider)
                .eq("provider_payment_id", pi_id)
                .maybe_single()
                .execute()
            )
            order = getattr(res, "data", None)
            if order:
                return order
            if provider == "stripe":
                res = await (
                    admin_sb.table("orders")
                    .select("*")
                    .eq("stripe_payment_intent", pi_id)
                    .maybe_single()
                    .execute()
                )
                return getattr(res, "data", None)
            return None
        except Exception as exc:
            logger.error("DB Error fetching order by provider payment %s: %s", pi_id, exc, exc_info=True)
            raise RuntimeError("Unable to resolve payment reference") from exc

    async def record_webhook_event(self, event_id: str, event_type: str, pi_id: Optional[str]) -> bool:
        admin_sb = await get_async_admin_supabase()
        provider = get_current_provider_key()
        try:
            res = await admin_sb.rpc(
                "claim_webhook_event_provider",
                {
                    "p_event_id": event_id,
                    "p_event_type": event_type,
                    "p_provider": provider,
                    "p_provider_payment_id": pi_id,
                },
            ).execute()
            data = getattr(res, "data", None)
            return True if data is None else bool(data)
        except Exception as exc:
            logger.error("DB Error claiming webhook event %s: %s", event_id, exc, exc_info=True)
            raise RuntimeError("Unable to claim webhook event") from exc

    async def mark_webhook_event_processed(self, event_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc("mark_webhook_event_processed", {"p_event_id": event_id}).execute()
        except Exception as exc:
            logger.error("DB Error marking webhook event %s: %s", event_id, exc, exc_info=True)
            raise RuntimeError("Unable to mark webhook event processed") from exc

    async def update_order_status_via_rpc(self, order_id: str, new_status: str, notes: str) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc(
                "rpc_admin_update_order_status",
                {"p_order_id": order_id, "p_new_status": new_status, "p_notes": notes},
            ).execute()
        except Exception as exc:
            logger.error("Webhook RPC Error updating status for %s: %s", order_id, exc, exc_info=True)
            raise RuntimeError("Unable to update order status") from exc

    async def list_stale_pending_orders(self, cutoff_iso: str) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await (
                admin_sb.table("orders")
                .select("id, customer_id, payment_provider, provider_payment_id, stripe_payment_intent, created_at")
                .eq("status", "pending")
                .lt("created_at", cutoff_iso)
                .execute()
            )
            return getattr(res, "data", None) or []
        except Exception as exc:
            logger.error("DB Error listing stale pending orders: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load stale pending orders") from exc
