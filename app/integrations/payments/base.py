"""
Payment Gateway Base Interface
Path: app/integrations/payments/base.py
"""
from abc import ABC, abstractmethod
from typing import Any

class PaymentProvider(ABC):
    @abstractmethod
    def create_payment_intent(self, amount: float, currency: str, order_id: str) -> dict:
        pass

    @abstractmethod
    def process_refund(self, payment_intent_id: str) -> bool:
        pass