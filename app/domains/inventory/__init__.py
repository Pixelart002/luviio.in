"""
Inventory Domain
================
Path: app/domains/inventory/__init__.py

Centralized stock management: reservations, availability checks, and stock adjustments.
"""
from app.domains.inventory.service import InventoryService

__all__ = ["InventoryService"]
