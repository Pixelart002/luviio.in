"""
Payment Messages & Security Rules (SSOT)
========================================
Path: app/constants/payment_messages.py
"""

class PaymentMessages:
    CONFIRMED = "Payment confirmed and order settled successfully."
    ALREADY_SETTLED = "This payment was already processed and settled."
    RETRY_SUCCESSFUL = "Payment was already successful! No retry needed."

class PaymentSecurityMessages:
    RATE_LIMIT = "Too many payment attempts. Please wait a moment."
    ALREADY_PAID = "This order has already been paid and cannot be modified."
    DUPLICATE_ORDER = "An order with this unique transaction key already exists."
    EMPTY_CART = "Your cart is empty. Please add items before proceeding to checkout."
    OUT_OF_STOCK = "Item '{name}' is currently out of stock or inactive."
    INVALID_AMOUNT = "Order total is below the minimum allowed amount of ₹{min_amount}."
    ADDRESS_NOT_FOUND = "The selected shipping address could not be found."
    PAYMENT_FAILED = "Payment processing failed. Please verify your details."
    INTENT_STATE_ERROR = "Payment session is in an unrecoverable state: {status}."
    UNAUTHORIZED_ACCESS = "You are not authorized to process payment for this order."
    ORDER_NOT_FOUND = "The referenced order could not be found."
    RACE_CONDITION = "Inventory depleted or Database error during checkout. Please try again."
    NO_INTENT_LINKED = "No payment intent is linked to this order."
    ACTIVE_PENDING_EXISTS = "You already have an active checkout session. Please complete your payment or cancel the pending order before starting a new one."

class PaymentRules:
    MIN_ORDER_AMOUNT_PAISE = 5000  # ₹50 minimum order
    BRUTE_FORCE_MAX_ATTEMPTS = 5
    BRUTE_FORCE_WINDOW_SEC = 60