"""Snapshot-backed adapter for the legacy PDF renderer.

The invoice PDF renderer is intentionally kept as a pure presentation layer,
but older versions read seller data from process environment variables. This
adapter supplies the immutable invoice snapshots at request time and maps
billing/shipping snapshots to the renderer's legacy order fields.
"""
from __future__ import annotations

import threading
from typing import Any

from app.utils.documents import pdf_invoice

_RENDER_LOCK = threading.RLock()


def _safe(value: Any) -> str:
    return "" if value is None else str(value).strip()


def build_snapshot_invoice_pdf(
    invoice_order: dict[str, Any],
    customer: dict[str, Any],
    seller_snapshot: dict[str, Any],
    billing_snapshot: dict[str, Any],
    shipping_snapshot: dict[str, Any],
) -> bytes:
    """Render a PDF exclusively from the immutable invoice snapshot.

    The lock is required because the existing renderer keeps seller settings
    in a module-level dictionary. It prevents concurrent requests from
    leaking one invoice's seller configuration into another PDF.
    """
    seller = seller_snapshot or {}
    billing = billing_snapshot or {}
    shipping = shipping_snapshot or {}

    render_order = dict(invoice_order)

    # Freeze both address blocks onto the renderer's expected field names.
    for prefix, snapshot in (("shipping", shipping), ("billing", billing)):
        render_order[f"{prefix}_name"] = snapshot.get("name")
        render_order[f"{prefix}_company_name"] = snapshot.get("company_name")
        render_order[f"{prefix}_phone"] = snapshot.get("phone")
        render_order[f"{prefix}_email"] = snapshot.get("email")
        render_order[f"{prefix}_line1"] = snapshot.get("line1")
        render_order[f"{prefix}_line2"] = snapshot.get("line2")
        render_order[f"{prefix}_landmark"] = snapshot.get("landmark")
        render_order[f"{prefix}_city"] = snapshot.get("city")
        render_order[f"{prefix}_district"] = snapshot.get("district")
        render_order[f"{prefix}_state"] = snapshot.get("state")
        render_order[f"{prefix}_postal_code"] = snapshot.get("postal_code")
        render_order[f"{prefix}_country"] = snapshot.get("country")
        render_order[f"{prefix}_gstin"] = snapshot.get("gstin")

    # The existing renderer expects these seller values from its module-level
    # _S dictionary. Replace them only for the duration of this render.
    seller_values = {
        "name": _safe(seller.get("legal_name")),
        "addr1": _safe(seller.get("address_1")),
        "addr2": _safe(seller.get("address_2")),
        "state": _safe(seller.get("state_code")) or _safe(seller.get("state")),
        "pan": _safe(seller.get("pan")),
        "gstin": _safe(seller.get("gstin")),
        "email": _safe(seller.get("email")),
        "website": _safe(seller.get("website")),
    }

    with _RENDER_LOCK:
        previous = dict(pdf_invoice._S)
        pdf_invoice._S.update(seller_values)
        try:
            return pdf_invoice.build_invoice_pdf(render_order, customer)
        finally:
            pdf_invoice._S.clear()
            pdf_invoice._S.update(previous)
