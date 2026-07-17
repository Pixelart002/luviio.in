"""
Payment Messages & Security Strings (SSOT)
==========================================
Path: app/constants/payment_messages.py
"""

class PaymentMessages:
    PAYMENT_CONFIRMED = "Payment confirmed and order settled successfully."
    PAYMENT_ALREADY_SETTLED = "This payment was already processed and settled."
    RETRY_SUCCESSFUL = "Payment was already successful! No retry needed."
    FAILURE_LOGGED = "Payment failure logged successfully. You can safely retry."

class PaymentSecurityMessages:
    RATE_LIMIT_EXCEEDED = "Too many payment attempts. Please wait a moment and try again."
    ALREADY_PAID = "This order has already been paid and cannot be modified."
    DUPLICATE_ORDER = "An order with this unique transaction key already exists."
    EMPTY_CART = "Your cart is empty. Please add items before checking out."
    INVALID_AMOUNT = "Order total is below the minimum allowed transaction amount."
    ADDRESS_NOT_FOUND = "The selected shipping address could not be verified."
    PAYMENT_FAILED = "Payment processing failed. Please verify your payment details."
    INTENT_STATE_ERROR = "Payment session is in an unrecoverable state. Please start a new checkout."
    UNAUTHORIZED_ORDER_ACCESS = "You are not authorized to process payment for this order."
    ORDER_NOT_FOUND = "The referenced order could not be found in the system."
    DB_SETTLEMENT_ERROR = "A critical error occurred while recording your payment. Please contact support."
    MISSING_INTENT_LINK = "This order is not linked to a valid payment session."