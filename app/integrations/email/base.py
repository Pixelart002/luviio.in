"""
Email Provider Base Interface (Adapter Pattern)
Path: app/integrations/email/base.py
"""
from abc import ABC, abstractmethod
from typing import Any, List

class EmailProvider(ABC):
    """Blueprint for any email provider (Resend, SES, Mailgun)"""
    
    @abstractmethod
    def send_welcome_email(self, to: str, name: str) -> None:
        pass

    @abstractmethod
    def send_order_confirmation(self, to: str, order: dict) -> None:
        pass

    @abstractmethod
    def send_order_shipped(self, to: str, order: dict, tracking_number: str) -> None:
        pass

    @abstractmethod
    def send_cart_reminder_email(self, to: str, name: str, items: list) -> None:
        pass