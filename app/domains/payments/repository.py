"""
Payments Repository -- ACID & JIT Hybrid Flow (Enterprise Grade & GST Ready)
============================================================================
Path: app/domains/payments/repository.py

Lifecycle-hardening changes in this version:
  * record_payment_attempt() -- THE single write path for both `payments`
    (one row per order -- the rollup header) and `payment_attempts` (one
    row per PaymentIntent -- the detail log). Called for intent creation,
    every retry, and failure recording. Success goes through
    settle_order_transaction() instead (needs its own order-status guard).
  * get_attempt_count() -- reads `total_attempts` directly off the order's
    lifecycle state.
"""

# Canonical repository implementation retained below.
