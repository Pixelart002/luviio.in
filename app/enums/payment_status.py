"""
Payment Status Enum
===================
Path: app/enums/payment_status.py
"""
from enum import Enum

class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"