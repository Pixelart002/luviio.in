"""
Inventory Enums
===============
Path: app/domains/inventory/enums.py

Moved from app/enums/stock_status.py
"""
from enum import Enum

class StockStatus(str, Enum):
    """Stock availability status for products."""
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LOW_STOCK = "low_stock"
