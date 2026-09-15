"""Payment provider plugin registry and runtime configuration adapter."""
from __future__ import annotations

from typing import Any, Dict, List, Type

from app.core.supabase import get_admin_supabase
from app.integrations.payments.base import PaymentProvider
from app.integrations.payments.stripe_impl import StripeProvider

PAYMENT_REGISTRY: Dict[str, Type[PaymentProvider]] = {"stripe": StripeProvider}


class ConfiguredPaymentProvider(PaymentProvider):
    """Provider adapter applying DB-backed activation and method settings."""

    def __init__(self, provider_key: str, provider: PaymentProvider) -> None:
        self.provider_key = provider_key
        self.provider = provider

    def _configuration(self) -> List[str]:
        sb = get_admin_supabase()
        plugin = sb.table("payment_provider_plugins").select("enabled").eq("provider_key", self.provider_key).limit(1).execute()
        rows = getattr(plugin, "data", None) or []
        if not rows or not rows[0].get("enabled"):
            raise RuntimeError(f"Payment provider '{self.provider_key}' is disabled.")
        methods = sb.table("payment_provider_methods").select("method_key").eq("provider_key", self.provider_key).eq("enabled", True).order("priority").execute()
        return [str(row["method_key"]).strip().lower() for row in (getattr(methods, "data", None) or []) if row.get("method_key")]

    def create_payment_intent(self, amount_paise: int, currency: str, order_id: str, user_id: str, idem_key: str, payment_method_types: List[str] | None = None) -> Dict[str, Any]:
        configured_methods = self._configuration()
        if not configured_methods:
            raise RuntimeError(f"No payment methods are enabled for '{self.provider_key}'.")
        return self.provider.create_payment_intent(amount_paise, currency, order_id, user_id, idem_key, payment_method_types or configured_methods)

    def update_intent_metadata(self, intent_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return self.provider.update_intent_metadata(intent_id, metadata)

    def retrieve_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        return self.provider.retrieve_intent(payment_intent_id)

    def verify_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        return self.provider.verify_webhook(payload, sig_header)

    def process_refund(self, payment_intent_id: str) -> bool:
        return self.provider.process_refund(payment_intent_id)

    def cancel_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        return self.provider.cancel_intent(payment_intent_id)


def get_payment_provider(provider_name: str = "stripe") -> PaymentProvider:
    key = provider_name.strip().lower()
    provider_class = PAYMENT_REGISTRY.get(key)
    if not provider_class:
        raise ValueError(f"Payment provider '{provider_name}' is not registered.")
    return ConfiguredPaymentProvider(key, provider_class())
