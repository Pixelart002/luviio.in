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
    INVALID_IDEMPOTENCY_KEY = "The provided idempotency key is not a valid UUID format."
    INVALID_METADATA = "Stripe webhook payload is missing required order binding metadata."
    ZERO_AMOUNT_RETRY = "This order has a zero or invalid balance and cannot be retried."

    # 🔥 NEW -- lifecycle hardening messages
    ORDER_NO_LONGER_RETRYABLE = (
        "This order can no longer be retried -- it was cancelled because checkout "
        "wasn't completed in time and the reserved stock was released. "
        "Please start a new order."
    )
    ORDER_CANCELLED_AUTO_REFUNDED = (
        "This order was already cancelled before your payment went through. "
        "Your payment has been automatically refunded and will reflect in your "
        "account within 5-10 business days."
    )
    TOO_MANY_ATTEMPTS = (
        "Too many failed payment attempts on this order. Please wait a few "
        "minutes, or place a new order to try a different payment method."
    )

class PaymentRules:
    MIN_ORDER_AMOUNT_PAISE = 5000  # ₹50 minimum order
    BRUTE_FORCE_MAX_ATTEMPTS = 5
    BRUTE_FORCE_WINDOW_SEC = 60

    # 🔥 NEW -- how long a 'pending' order is allowed to sit with no
    # successful payment before the abandoned-checkout sweep cancels it
    # and releases the reserved stock. Kept here (not hardcoded in the
    # cron file) so it's one single source of truth.
    ABANDONED_ORDER_TIMEOUT_MINUTES = 30