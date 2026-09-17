"""Compatibility entry point for the immutable snapshot invoice renderer."""
from __future__ import annotations

from typing import Any

from app.utils.documents.invoice_pdf_renderer_v2 import build_snapshot_invoice_pdf as _render


def build_snapshot_invoice_pdf(
    invoice_order: dict[str, Any],
    customer: dict[str, Any],
    seller_snapshot: dict[str, Any],
    billing_snapshot: dict[str, Any],
    shipping_snapshot: dict[str, Any],
) -> bytes:
    """Render strictly from the frozen invoice snapshots."""
    return _render(
        invoice_order,
        customer,
        seller_snapshot,
        billing_snapshot,
        shipping_snapshot,
    )
