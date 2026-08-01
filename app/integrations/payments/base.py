"""
Payment Gateway Base Interface
==============================
Path: app/integrations/payments/base.py
"""
from abc import ABC, abstractmethod
from typing import Any, Dict

class PaymentProvider(ABC):
    @abstractmethod
    def create_payment_intent(
        self, 
        amount_paise: int, 
        currency: str, 
        order_id: str, 
        user_id: str, 
        idem_key: str
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def update_intent_metadata(self, intent_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def retrieve_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def verify_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def process_refund(self, payment_intent_id: str) -> bool:
        pass

    # 🔥 NEW -- explicitly cancels a PaymentIntent on Stripe's side.
    # Used by the abandoned-checkout cron (and anywhere else we decide an
    # order is dead) so a customer's browser can never complete a stale
    # checkout page AFTER we've already released the reserved stock in our
    # own DB. Without this, DB-side cancellation alone leaves a "zombie"
    # PaymentIntent that Stripe will happily still confirm.
    @abstractmethod
    def cancel_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        pass