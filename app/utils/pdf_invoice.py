"""
PDF Invoice Builder — reportlab
================================
Generates a branded Luviio invoice PDF entirely in memory (BytesIO).
No disk writes — the bytes are streamed directly to the HTTP response.

Usage:
    from app.utils.pdf_invoice import build_invoice_pdf
    pdf_bytes = build_invoice_pdf(order, customer)

Design:
  • A4 page, portrait
  • Brand colours: Navy #0B1628 (bg), Teal #00C5D4 (accent), White text
  • Sections: header → order meta → items table → pricing summary → footer
  • Numbers always 2dp, currency INR (₹)
  • Invoice number = INV-{order_id[:8].upper()} for uniqueness
"""
from __future__ import annotations

import io
import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

logger = logging.getLogger(__name__)

# ── Font Setup for Rupee (₹) Support ──────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_DIR, "fonts")

# Fallback fonts just in case TTF files are missing
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

try:
    # Register Roboto fonts
    pdfmetrics.registerFont(TTFont("Roboto", os.path.join(_FONT_DIR, "Roboto-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Roboto-Bold", os.path.join(_FONT_DIR, "Roboto-Bold.ttf")))
    
    # Register family so <b> HTML tags work mapped to the bold font
    registerFontFamily("Roboto", normal="Roboto", bold="Roboto-Bold")
    
    _FONT_REGULAR = "Roboto"
    _FONT_BOLD = "Roboto-Bold"
    logger.info("Custom fonts loaded successfully for Rupee symbol support.")
except Exception as e:
    logger.warning(f"Failed to load custom fonts. Falling back to Helvetica. Rupee symbol may not render. Error: {e}")


# ── Brand palette ─────────────────────────────────────────────────────────────
_NAVY  = colors.HexColor("#0B1628")
_TEAL  = colors.HexColor("#00C5D4")
_GOLD  = colors.HexColor("#C9A96E")
_LIGHT = colors.HexColor("#F4F4F4")
_GREY  = colors.HexColor("#888888")
_WHITE = colors.white
_BLACK = colors.HexColor("#1A1A1A")

# ── Page geometry ─────────────────────────────────────────────────────────────
_W, _H   = A4             # 595 × 842 pt
_MARGIN  = 20 * mm        # 20mm all sides


# ── Style helpers ─────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    return {
        "brand": ParagraphStyle(
            "brand",
            fontSize=26,
            leading=30,
            textColor=_TEAL,
            fontName=_FONT_BOLD,
            letterSpacing=3,
        ),
        "tagline": ParagraphStyle(
            "tagline",
            fontSize=8,
            leading=10,
            textColor=_GREY,
            fontName=_FONT_REGULAR,
        ),
        "invoice_title": ParagraphStyle(
            "invoice_title",
            fontSize=18,
            leading=22,
            textColor=_NAVY,
            fontName=_FONT_BOLD,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontSize=10,
            leading=14,
            textColor=_NAVY,
            fontName=_FONT_BOLD,
        ),
        "body": ParagraphStyle(
            "body",
            fontSize=9,
            leading=13,
            textColor=_BLACK,
            fontName=_FONT_REGULAR,
        ),
        "small": ParagraphStyle(
            "small",
            fontSize=8,
            leading=11,
            textColor=_GREY,
            fontName=_FONT_REGULAR,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontSize=7.5,
            leading=11,
            textColor=_GREY,
            fontName=_FONT_REGULAR,
            alignment=1,   # center
        ),
        "total_label": ParagraphStyle(
            "total_label",
            fontSize=11,
            leading=15,
            textColor=_NAVY,
            fontName=_FONT_BOLD,
        ),
        "total_value": ParagraphStyle(
            "total_value",
            fontSize=13,
            leading=17,
            textColor=_TEAL,
            fontName=_FONT_BOLD,
        ),
    }


def _fmt(amount: Any, symbol: str = "₹") -> str:
    """Format a number as currency string."""
    try:
        return f"{symbol}{float(amount):,.2f}"
    except (TypeError, ValueError):
        return f"{symbol}0.00"


def _addr_lines(order: dict[str, Any]) -> str:
    """Build a shipping address block from order fields."""
    parts = [
        order.get("shipping_line1", ""),
        order.get("shipping_line2", ""),
        order.get("shipping_city", ""),
        order.get("shipping_state", ""),
        order.get("shipping_postal_code", ""),
        order.get("shipping_country", ""),
    ]
    return ", ".join(p for p in parts if p)


# ── Public API ─────────────────────────────────────────────────────────────────

def build_invoice_pdf(
    order:    dict[str, Any],
    customer: dict[str, Any],
) -> bytes:
    """
    Build a complete invoice PDF in memory and return raw bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"Invoice — {order.get('id', '')[:8].upper()}",
        author="Luviio",
    )

    s     = _styles()
    story = []

    order_id   = str(order.get("id", ""))
    invoice_no = f"INV-{order_id[:8].upper()}"
    created_at = order.get("created_at", "")
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            date_str = dt.strftime("%d %B %Y")
        except Exception:
            date_str = str(created_at)[:10]
    else:
        date_str = datetime.now(timezone.utc).strftime("%d %B %Y")

    # ── HEADER — dark navy bar with brand name ────────────────────────────────
    header_data = [[
        Paragraph("LUVIIO", s["brand"]),
        Paragraph(f"<b>INVOICE</b><br/>{invoice_no}", ParagraphStyle(
            "inv_no",
            fontSize=14,
            leading=18,
            textColor=_WHITE,
            fontName=_FONT_BOLD,
            alignment=2,  # right
        )),
    ]]
    header_tbl = Table(header_data, colWidths=[(_W - 2 * _MARGIN) * 0.6, (_W - 2 * _MARGIN) * 0.4])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), _NAVY),
        ("TEXTCOLOR",   (0, 0), (-1, -1), _WHITE),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (0, -1), 14),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 14),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6 * mm))

    # ── META ROW — billed to | order details ─────────────────────────────────
    customer_name  = customer.get("full_name") or "Customer"
    customer_email = customer.get("email", "")
    addr           = _addr_lines(order)

    meta_left = (
        f"<b>Billed To</b><br/>"
        f"{customer_name}<br/>"
        f"{customer_email}<br/>"
        f"{addr}"
    )
    meta_right = (
        f"<b>Invoice No:</b> {invoice_no}<br/>"
        f"<b>Order ID:</b> #{order_id[:8].upper()}<br/>"
        f"<b>Date:</b> {date_str}<br/>"
        f"<b>Status:</b> {str(order.get('status', '')).capitalize()}"
    )

    col_w = (_W - 2 * _MARGIN) / 2
    meta_tbl = Table(
        [[Paragraph(meta_left, s["body"]), Paragraph(meta_right, s["body"])]],
        colWidths=[col_w, col_w],
    )
    meta_tbl.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_TEAL))
    story.append(Spacer(1, 5 * mm))

    # ── ITEMS TABLE ───────────────────────────────────────────────────────────
    story.append(Paragraph("Order Items", s["h2"]))
    story.append(Spacer(1, 3 * mm))

    items_raw = order.get("order_items") or []
    item_rows: list[dict[str, Any]] = []
    for item in items_raw:
        if isinstance(item, dict):
            item_rows.append(item)

    col_widths = [
        (_W - 2 * _MARGIN) * 0.45,  # Product
        (_W - 2 * _MARGIN) * 0.12,  # Qty
        (_W - 2 * _MARGIN) * 0.20,  # Unit Price
        (_W - 2 * _MARGIN) * 0.23,  # Subtotal
    ]

    # Header row
    tbl_data = [[
        Paragraph("<b>Product</b>",    s["body"]),
        Paragraph("<b>Qty</b>",        s["body"]),
        Paragraph("<b>Unit Price</b>", s["body"]),
        Paragraph("<b>Subtotal</b>",   s["body"]),
    ]]

    for item in item_rows:
        name      = item.get("product_name") or "—"
        qty       = item.get("quantity", 0)
        unit_p    = item.get("unit_price", 0)
        subtotal  = item.get("subtotal") or (float(unit_p) * qty)
        tbl_data.append([
            Paragraph(name, s["body"]),
            Paragraph(str(qty), s["body"]),
            Paragraph(_fmt(unit_p), s["body"]),
            Paragraph(_fmt(subtotal), s["body"]),
        ])

    if not item_rows:
        tbl_data.append([Paragraph("No items found.", s["small"]), "", "", ""])

    items_tbl = Table(tbl_data, colWidths=col_widths, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _LIGHT]),
        ("FONTSIZE",      (0, 1), (-1, -1), 8.5),
        # Borders
        ("LINEBELOW",     (0, 0), (-1, 0), 1, _TEAL),
        ("LINEBELOW",     (0, 1), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        # Padding
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        # Right-align numeric columns
        ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",         (0, 0), (0, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 5 * mm))

    # ── PRICING SUMMARY ───────────────────────────────────────────────────────
    sub_amt  = order.get("subtotal",      0)
    ship_amt = order.get("shipping_cost", 0)
    tax_amt  = order.get("tax_amount",    0)
    total    = order.get("total_amount",  0)

    summary_data = [
        ["Subtotal",  _fmt(sub_amt)],
        ["Shipping",  _fmt(ship_amt) if float(ship_amt or 0) > 0 else "FREE"],
        ["Tax (GST)", _fmt(tax_amt)],
    ]

    summary_col_w = (_W - 2 * _MARGIN) * 0.3
    sum_tbl = Table(
        summary_data,
        colWidths=[summary_col_w, summary_col_w],
        hAlign="RIGHT",
    )
    sum_tbl.setStyle(TableStyle([
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("FONTNAME",      (0, 0), (0, -1), _FONT_REGULAR),
        ("FONTNAME",      (1, 0), (1, -1), _FONT_REGULAR),
        ("TEXTCOLOR",     (0, 0), (0, -1), _GREY),
        ("TEXTCOLOR",     (1, 0), (1, -1), _BLACK),
        ("ALIGN",         (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.5, _GREY),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 2 * mm))

    # Total row — larger, teal
    total_data = [["TOTAL", _fmt(total)]]
    total_tbl  = Table(
        total_data,
        colWidths=[summary_col_w, summary_col_w],
        hAlign="RIGHT",
    )
    total_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, -1), _TEAL),
        ("FONTNAME",      (0, 0), (-1, -1), _FONT_BOLD),
        ("FONTSIZE",      (0, 0), (-1, -1), 12),
        ("ALIGN",         (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story.append(total_tbl)
    story.append(Spacer(1, 8 * mm))

    # ── NOTES ─────────────────────────────────────────────────────────────────
    notes = order.get("notes")
    if notes:
        story.append(HRFlowable(width="100%", thickness=0.3, color=_GREY))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("<b>Notes</b>", s["h2"]))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(notes, s["body"]))
        story.append(Spacer(1, 5 * mm))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_TEAL))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Thank you for shopping with Luviio · luviio.in · orders@luviio.in<br/>"
        "This is a computer-generated invoice and does not require a signature.",
        s["footer"],
    ))

    # ── BUILD ─────────────────────────────────────────────────────────────────
    try:
        doc.build(story)
    except Exception as exc:
        logger.error("PDF build failed | order=%.8s | %s", order_id, exc)
        raise RuntimeError(f"Invoice generation failed: {exc}") from exc

    pdf_bytes = buf.getvalue()
    logger.info("Invoice PDF built | order=%.8s | size=%d bytes", order_id, len(pdf_bytes))
    return pdf_bytes
