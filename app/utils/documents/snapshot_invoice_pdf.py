"""Compatibility entry point for the immutable snapshot invoice renderer."""
from __future__ import annotations

from typing import Any

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

from app.utils.documents import invoice_pdf_renderer_v3 as _renderer


def _safe_qr(data: str, size: float = 68) -> Drawing:
    widget = QrCodeWidget(data or "LUVIIO")
    x1, y1, x2, y2 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x2-x1), 0, 0, size / (y2-y1), 0, 0])
    drawing.add(widget)
    return drawing


_renderer._qr = _safe_qr
build_snapshot_invoice_pdf = _renderer.build_snapshot_invoice_pdf
