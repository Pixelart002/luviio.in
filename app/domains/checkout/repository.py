"""Checkout persistence boundary.

This repository owns data access required to assemble and persist checkout
transactions. Payment-domain repositories remain responsible for payment-only
operations; checkout must not reach into that domain's repository.
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class AsyncCheckoutRepository:
    """Persistence adapter for checkout use-cases."""

    async def has_active_pending_order(self, user_id: str) -> bool:
        sb = await get_async_admin_supabase()
        try:
            res = (
                await sb.table("orders")
                .select("id")
                .eq("customer_id", user_id)
                .eq("status", "pending")
                .limit(1)
                .execute()
            )
            return bool(getattr(res, "data", None))
        except Exception as exc:
            logger.error("DB error checking pending orders: %s", exc, exc_info=True)
            raise RuntimeError("Unable to verify active pending orders") from exc

    async def get_cart_items_for_checkout(self, user_id: str) -> List[Dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("carts")
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
            logger.error("DB error loading checkout cart: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load checkout cart") from exc

    async def get_shipping_address(self, address_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = (
                await sb.table("addresses")
                .select("*")
                .eq("id", address_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB error loading address: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load checkout address") from exc

    async def get_customer_email(self, user_id: str) -> str:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("users")
                .select("email")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            data = getattr(res, "data", None)
            if not data or not data.get("email"):
                raise RuntimeError("Customer email is missing")
            return data["email"]
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("DB error loading customer email: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load customer email") from exc

    async def get_order_by_idempotency_key(self, user_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("orders")
                .select("*")
                .eq("customer_id", user_id)
                .eq("idempotency_key", idempotency_key)
                .maybe_single()
                .execute()
            )
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB error checking idempotency key: %s", exc, exc_info=True)
            raise RuntimeError("Unable to verify idempotency key") from exc

    async def get_pricing_config(self) -> Dict[str, Any]:
        """Read the canonical pricing projection from system_settings."""
        sb = await get_async_admin_supabase()
        try:
            res = await sb.rpc("get_canonical_pricing_config").execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("Canonical pricing configuration is missing")
            return data
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("DB error loading pricing configuration: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load pricing configuration") from exc

    async def create_pending_order_with_reservation(
        self, order_data: Dict[str, Any], items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.rpc(
                "create_pending_order_with_reservation",
                {"p_order_data": order_data, "p_items": items},
            ).execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("Checkout reservation RPC returned no order")
            return data
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("Checkout reservation RPC failed: %s", exc, exc_info=True)
            raise RuntimeError("Unable to reserve checkout order") from exc

    async def clear_order_payment_intent(self, order_id: str, expected_pi_id: str) -> bool:
        """Detach a stale online-payment intent during safe COD conversion."""
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("orders")
                .update({"stripe_payment_intent": None})
                .eq("id", order_id)
                .eq("status", "pending")
                .eq("stripe_payment_intent", expected_pi_id)
                .execute()
            )
            return bool(getattr(res, "data", None))
        except Exception as exc:
            logger.error("DB error clearing payment intent: %s", exc, exc_info=True)
            raise RuntimeError("Unable to update checkout payment state") from exc
