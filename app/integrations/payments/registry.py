"""Payment provider plugin registry and runtime configuration adapter."""
from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any, Dict, List, Type

from app.core.supabase import get_admin_supabase
from app.integrations.payments.base import PaymentProvider
from app.integrations.payments.context import get_current_provider_key
from app.integrations.payments.stripe_impl import StripeProvider

PAYMENT_REGISTRY: Dict[str, Type[PaymentProvider]] = {"stripe": StripeProvider}


def register_payment_provider(provider_key: str, provider_class: Type[PaymentProvider], *, replace: bool = False) -> None:
    """Register provider implementation code at application/plugin load time."""
    key = provider_key.strip().lower()
    if not key or len(key) > 64 or not key.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Invalid payment provider key.")
    if not issubclass(provider_class, PaymentProvider):
        raise TypeError("Payment provider must implement PaymentProvider.")
    if key in PAYMENT_REGISTRY and not replace:
        raise ValueError(f"Payment provider '{key}' is already registered.")
    PAYMENT_REGISTRY[key] = provider_class


def discover_payment_plugins() -> List[str]:
    """Discover trusted installed Python payment-provider plugins."""
    discovered: List[str] = []
    try:
        eps = entry_points()
        group = eps.select(group="luviio.payment_providers") if hasattr(eps, "select") else eps.get("luviio.payment_providers", [])
    except Exception:
        return discovered

    for ep in group:
        try:
            loaded = ep.load()
            key = ep.name.strip().lower()
            if isinstance(loaded, type) and issubclass(loaded, PaymentProvider):
                register_payment_provider(key, loaded)
            elif callable(loaded):
                loaded()
            else:
                raise TypeError(f"Plugin '{ep.name}' does not expose a PaymentProvider or registration callable.")
            if key in PAYMENT_REGISTRY:
                discovered.append(key)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Payment plugin discovery failed for %s: %s", ep.name, exc, exc_info=True)
    return discovered


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

    def process_refund(
        self,
        payment_intent_id: str,
        amount_paise: int | None = None,
        idempotency_key: str | None = None,
        reason: str | None = None,
    ) -> Dict[str, Any]:
        return self.provider.process_refund(
            payment_intent_id,
            amount_paise=amount_paise,
            idempotency_key=idempotency_key,
            reason=reason,
        )

    def cancel_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        return self.provider.cancel_intent(payment_intent_id)


def get_payment_provider(provider_name: str = "stripe") -> PaymentProvider:
    requested = get_current_provider_key()
    key = requested if provider_name.strip().lower() == "stripe" and requested != "stripe" else provider_name.strip().lower()
    provider_class = PAYMENT_REGISTRY.get(key)
    if not provider_class:
        raise ValueError(f"Payment provider '{provider_name}' is not registered.")
    return ConfiguredPaymentProvider(key, provider_class())


try:
    discover_payment_plugins()
except Exception:
    pass
