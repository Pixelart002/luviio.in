"""
Email Provider Base Interface (Adapter Pattern)
Path: app/integrations/email/base.py
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class EmailProvider(ABC):
    """Blueprint for any email provider (Resend, SES, Mailgun)"""
    
    @abstractmethod
    async def send_welcome_email(self, to: str, name: str) -> None:
        pass

    @abstractmethod
    async def send_order_confirmation(self, to: str, order: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    async def send_order_shipped(self, to: str, order: Dict[str, Any], tracking_number: str) -> None:
        pass

    @abstractmethod
    async def send_cart_reminder_email(self, to: str, name: str, items: List[Any]) -> None:
        pass

    @abstractmethod
    async def send_payment_success(self, to: str, order: Dict[str, Any]) -> None:
        pass