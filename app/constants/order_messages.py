"""
Order Messages & Security Strings (SSOT)
========================================
Path: app/constants/order_messages.py
"""

class OrderMessages:
    CANCEL_SUCCESS = "Order has been successfully cancelled and stock restored."
    UPDATE_SUCCESS = "Order status and metadata updated successfully."
    INVOICE_GENERATED = "Invoice PDF generated successfully."

class OrderSecurityMessages:
    ORDER_NOT_FOUND = "The requested order does not exist or you do not have permission to view it."
    UNAUTHORIZED_ACCESS = "Security Violation: You are not authorized to access or modify this order."
    INVALID_CANCEL_STATE = "This order cannot be cancelled because it has already been shipped, delivered, or refunded."
    INVALID_TRANSITION = "The requested order status transition is not permitted by business rules."
    REFUND_FAILED = "Payment gateway failed to process the refund. Please verify with Stripe dashboard."
    CONCURRENCY_CONFLICT = "Order state was modified by another transaction. Please refresh and try again."
    INVOICE_UNAVAILABLE = "Invoice PDF is only available for paid, shipped, delivered, or refunded orders."
    PDF_GENERATION_FAILED = "An internal error occurred while generating the invoice document."