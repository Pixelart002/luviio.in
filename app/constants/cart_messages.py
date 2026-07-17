"""
Cart Messages & Security Strings (SSOT)
=======================================
Path: app/constants/cart_messages.py
"""

class CartMessages:
    ITEM_ADDED = "Item added successfully."
    ITEM_UPDATED = "Line item quantity successfully committed."
    ITEM_REMOVED = "Item removed from cart."
    CART_CLEARED = "Cart cleared successfully."
    REMINDER_SENT = "Reminder successfully dispatched."

class CartSecurityMessages:
    PRODUCT_NOT_FOUND = "The requested product does not exist or is no longer active."
    OUT_OF_STOCK = "Insufficient stock available for the requested product."
    MAX_QTY_EXCEEDED = "You cannot add more than 100 units of a single item to your cart."
    ITEM_NOT_IN_CART = "The specified product is not present in your active cart ledger."
    CART_NOT_FOUND = "The targeted cart could not be resolved in the database."
    EMPTY_CART_REMINDER = "The cart is empty. No reminder dispatch is required."
    UNAUTHORIZED_ACCESS = "You do not have permission to access or modify this cart resource."