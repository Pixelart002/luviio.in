"""
Orders Domain
=============
Path: app/domains/orders/__init__.py

Owns the order lifecycle: creation from cart, FSM state transitions,
cancellation, admin updates, invoice generation.
"""
from app.domains.orders.policy import OrderPolicy
from app.domains.orders.repository import AsyncOrderRepository
from app.domains.orders.service import OrderService

__all__ = ["OrderService", "OrderPolicy", "AsyncOrderRepository"]
