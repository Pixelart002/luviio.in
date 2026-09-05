"""
Shipping Domain — configurable delivery methods & rate computation
===================================================================
Path: app/domains/shipping/__init__.py

Previously shipping cost was a hardcoded flat amount inside order creation.
This domain makes shipping a first-class, configurable concern:

  * `shipping_methods` table — {flat, free_threshold, per_item, weight} methods.
  * Admin CRUD + a public "compute rate" endpoint used by checkout.
  * The rate computation consumes the same dynamic store settings the order
    flow uses (standard_shipping_cost / free_shipping_threshold) as a safe
    default when no explicit method is configured, so nothing regresses.

Order pricing itself (GST, totals) stays in `app/domains/pricing` + orders —
shipping just contributes the `shipping_cost` line.
"""
from app.domains.shipping.router import router

__all__ = ["router"]
