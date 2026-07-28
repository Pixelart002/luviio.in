"""
Cart Messages & Security Rules (SSOT)
=====================================
Path: app/constants/cart_messages.py
"""

class CartMessages:
    ITEM_ADDED = "Item added to cart successfully."
    ITEM_UPDATED = "Cart item quantity updated successfully."
    ITEM_REMOVED = "Item removed from cart."
    CART_CLEARED = "All items removed from cart."
    REMINDER_SENT = "Abandoned cart reminder dispatched successfully."

class CartSecurityMessages:
    ITEM_NOT_FOUND = "The requested item is not in your cart."
    CART_NOT_FOUND = "The requested cart could not be found."
    EMPTY_CART_REMINDER = "Cart is empty. No reminder needed."
    OUT_OF_STOCK = "Only {stock} units available for '{name}'."
    PRODUCT_UNAVAILABLE = "Product '{name}' is currently unavailable or inactive."
    LIMIT_EXCEEDED = "Maximum {limit} units allowed per item in the cart."
    DB_OPERATION_FAILED = "An internal database error occurred while processing your cart request."

class CartRules:
    MAX_QTY_PER_ITEM = 100