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
  • Brand colors: Dark #080808, Gold #c9a55e, White text
  • GST-compliant format (India)
  • Sections: header → bill to/ship to → items table → tax breakup → total → footer
  • Numbers always 2 decimal places, currency INR (₹)
  • Invoice number = INV-{order_id[:8].upper()}
  • HSN column for GST compliance
  • Tax breakup: CGST + SGCT (or IGST for inter-state)
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
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

logger = logging.getLogger(__name__)

# ── Font Setup for Rupee (₹) Support ──────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_DIR, "fonts")

_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

try:
    pdfmetrics.registerFont(TTFont("Roboto", os.path.join(_FONT_DIR, "Roboto-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Roboto-Bold", os.path.join(_FONT_DIR, "Roboto-Bold.ttf")))
    registerFontFamily("Roboto", normal="Roboto", bold="Roboto-Bold")
    _FONT_REGULAR = "Roboto"
    _FONT_BOLD = "Roboto-Bold"
    logger.info("Custom fonts loaded for Rupee symbol support")
except Exception as e:
    logger.warning(f"Custom fonts failed — falling back to Helvetica: {e}")


# ── Brand Colors (Luviio Dark Theme) ──────────────────────────────────────────
BG_DARK    = colors.HexColor("#080808")
BG_SURFACE = colors.HexColor("#0d0c0a")
GOLD       = colors.HexColor("#c9a55e")
GOLD_DIM   = colors.HexColor("#2a2520")
TEXT       = colors.HexColor("#f0ece4")
TEXT_MUTED = colors.HexColor("#7a7368")
BORDER     = colors.HexColor("#1e1c18")
WHITE      = colors.white
SUCCESS    = colors.HexColor("#88dc88")

# ── Page geometry ─────────────────────────────────────────────────────────────
_W, _H  = A4             # 595 × 842 pt
_MARGIN = 18 * mm        # 18mm all sides


# ── Style Helpers ─────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    """All paragraph styles used in the invoice"""
    return {
        "brand": ParagraphStyle(
            "brand", fontSize=28, leading=32, textColor=GOLD,
            fontName=_FONT_BOLD, letterSpacing=4, alignment=TA_LEFT,
        ),
        "brand_sub": ParagraphStyle(
            "brand_sub", fontSize=8, leading=10, textColor=TEXT_MUTED,
            fontName=_FONT_REGULAR, alignment=TA_LEFT,
        ),
        "invoice_title": ParagraphStyle(
            "invoice_title", fontSize=16, leading=20, textColor=GOLD,
            fontName=_FONT_BOLD, alignment=TA_RIGHT,
        ),
        "section_title": ParagraphStyle(
            "section_title", fontSize=10, leading=14, textColor=TEXT,
            fontName=_FONT_BOLD, spaceBefore=8, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontSize=9, leading=13, textColor=TEXT,
            fontName=_FONT_REGULAR,
        ),
        "body_muted": ParagraphStyle(
            "body_muted", fontSize=8, leading=12, textColor=TEXT_MUTED,
            fontName=_FONT_REGULAR,
        ),
        "small": ParagraphStyle(
            "small", fontSize=7, leading=10, textColor=TEXT_MUTED,
            fontName=_FONT_REGULAR,
        ),
        "footer": ParagraphStyle(
            "footer", fontSize=7, leading=10, textColor=TEXT_MUTED,
            fontName=_FONT_REGULAR, alignment=TA_CENTER,
        ),
        "table_header": ParagraphStyle(
            "table_header", fontSize=8, leading=11, textColor=GOLD,
            fontName=_FONT_BOLD,
        ),
        "table_cell": ParagraphStyle(
            "table_cell", fontSize=8, leading=11, textColor=TEXT,
            fontName=_FONT_REGULAR,
        ),
        "table_cell_right": ParagraphStyle(
            "table_cell_right", fontSize=8, leading=11, textColor=TEXT,
            fontName=_FONT_REGULAR, alignment=TA_RIGHT,
        ),
        "total_label": ParagraphStyle(
            "total_label", fontSize=11, leading=15, textColor=TEXT,
            fontName=_FONT_BOLD,
        ),
        "total_value": ParagraphStyle(
            "total_value", fontSize=13, leading=17, textColor=GOLD,
            fontName=_FONT_BOLD, alignment=TA_RIGHT,
        ),
    }


def _fmt(amount: Any, symbol: str = "₹") -> str:
    """Format a number as Indian currency string"""
    try:
        return f"{symbol}{float(amount):,.2f}"
    except (TypeError, ValueError):
        return f"{symbol}0.00"


def _short_id(uuid_str: str) -> str:
    """Shorten UUID for display"""
    return uuid_str[:8].upper() if uuid_str else "—"


def _addr_block(order: dict[str, Any]) -> str:
    """Build a shipping address block"""
    parts = [
        order.get("shipping_line1", ""),
        order.get("shipping_line2", ""),
        order.get("shipping_city", ""),
        order.get("shipping_state", ""),
        order.get("shipping_postal_code", ""),
        order.get("shipping_country", ""),
    ]
    return "<br/>".join(p for p in parts if p)


def _calculate_gst_breakdown(order: dict[str, Any]) -> dict[str, float]:
    """
    Calculate CGST + SGST (intra-state) or IGST (inter-state).
    For simplicity, assumes intra-state (CGST 50% + SGST 50%).
    """
    tax_total = float(order.get("tax_amount", 0))
    return {
        "cgst": round(tax_total / 2, 2),
        "sgst": round(tax_total / 2, 2),
        "total": tax_total,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def build_invoice_pdf(
    order: dict[str, Any],
    customer: dict[str, Any],
) -> bytes:
    """
    Build a complete GST-compliant invoice PDF in memory and return raw bytes.
    
    Args:
        order: Full order object with items, pricing, addresses
        customer: User profile with email, full_name
    
    Returns:
        PDF file as bytes (ready to stream to client)
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"Invoice-{_short_id(order.get('id', ''))}",
        author="Luviio",
    )

    s = _styles()
    story = []

    # ── Extract data ──────────────────────────────────────────────────────────
    order_id   = str(order.get("id", ""))
    invoice_no = f"INV-{_short_id(order_id)}"
    
    created_at = order.get("created_at", "")
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        date_str = dt.strftime("%d %B %Y, %I:%M %p")
    except Exception:
        date_str = datetime.now(timezone.utc).strftime("%d %B %Y")

    customer_name = customer.get("full_name") or "Customer"
    customer_email = customer.get("email", "")
    ship_addr = _addr_block(order)
    status = str(order.get("status", "")).upper()
    tracking = order.get("tracking_number", "")

    # ══════════════════════════════════════════════════════════════════════════
    # 1. HEADER — Brand + Invoice Title
    # ══════════════════════════════════════════════════════════════════════════
    
    header_data = [
        [
            Paragraph("LUVIIO", s["brand"]),
            Paragraph("<b>TAX INVOICE</b>", s["invoice_title"]),
        ],
        [
            Paragraph("Premium Bath & Sanitation Products", s["brand_sub"]),
            Paragraph(invoice_no, s["body_muted"]),
        ],
    ]
    
    header_tbl = Table(header_data, colWidths=[(_W - 2*_MARGIN)*0.55, (_W - 2*_MARGIN)*0.45])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD))
    story.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════════════════════════════════════
    # 2. COMPANY + ORDER INFO
    # ══════════════════════════════════════════════════════════════════════════
    
    col_w = (_W - 2*_MARGIN) / 2
    
    company_info = Table([
        [
            # Left: Company Details
            Table([
                [Paragraph("<b>From:</b>", s["section_title"])],
                [Paragraph("Luviio Luxury Bath & Sanitation<br/>India<br/>support@luviio.in<br/>luviio.in", s["body_muted"])],
            ], colWidths=[col_w - 4*mm]),
            # Right: Order Details
            Table([
                [Paragraph("<b>Order Details</b>", s["section_title"])],
                [Paragraph(
                    f"<b>Invoice No:</b> {invoice_no}<br/>"
                    f"<b>Order ID:</b> #{_short_id(order_id)}<br/>"
                    f"<b>Date:</b> {date_str}<br/>"
                    f"<b>Status:</b> {status}",
                    s["body_muted"]
                )],
            ], colWidths=[col_w - 4*mm]),
        ]
    ], colWidths=[col_w, col_w])
    company_info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(company_info)
    story.append(Spacer(1, 5*mm))

    # ══════════════════════════════════════════════════════════════════════════
    # 3. BILL TO + SHIP TO
    # ══════════════════════════════════════════════════════════════════════════
    
    bill_ship = Table([
        [
            Table([
                [Paragraph("<b>Bill To:</b>", s["section_title"])],
                [Paragraph(f"{customer_name}<br/>{customer_email}", s["body_muted"])],
            ], colWidths=[col_w - 4*mm]),
            Table([
                [Paragraph("<b>Ship To:</b>", s["section_title"])],
                [Paragraph(ship_addr or "—", s["body_muted"])],
            ], colWidths=[col_w - 4*mm]),
        ]
    ], colWidths=[col_w, col_w])
    bill_ship.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(bill_ship)
    story.append(Spacer(1, 6*mm))
    
    if tracking:
        story.append(Paragraph(f"<b>Tracking:</b> {tracking}", s["body_muted"]))
        story.append(Spacer(1, 3*mm))

    # ══════════════════════════════════════════════════════════════════════════
    # 4. ITEMS TABLE (GST-compliant with HSN column)
    # ══════════════════════════════════════════════════════════════════════════
    
    story.append(Paragraph("<b>ORDER ITEMS</b>", s["section_title"]))
    story.append(Spacer(1, 3*mm))

    items_raw = order.get("order_items") or []

    # Column widths: # | Description | HSN | Qty | Rate | Amount
    col_widths = [
        (_W - 2*_MARGIN) * 0.05,   # #
        (_W - 2*_MARGIN) * 0.35,   # Description
        (_W - 2*_MARGIN) * 0.10,   # HSN
        (_W - 2*_MARGIN) * 0.08,   # Qty
        (_W - 2*_MARGIN) * 0.18,   # Rate
        (_W - 2*_MARGIN) * 0.24,   # Amount
    ]

    # Header
    tbl_data = [[
        Paragraph("<b>#</b>", s["table_header"]),
        Paragraph("<b>Description</b>", s["table_header"]),
        Paragraph("<b>HSN</b>", s["table_header"]),
        Paragraph("<b>Qty</b>", s["table_header"]),
        Paragraph("<b>Rate</b>", s["table_header"]),
        Paragraph("<b>Amount</b>", s["table_header"]),
    ]]

    for i, item in enumerate(items_raw, 1):
        name = item.get("product_name") or "—"
        qty = item.get("quantity", 0)
        rate = float(item.get("unit_price", 0))
        amount = float(item.get("subtotal", rate * qty))
        
        tbl_data.append([
            Paragraph(str(i), s["table_cell"]),
            Paragraph(name, s["table_cell"]),
            Paragraph("—", s["table_cell"]),  # HSN placeholder
            Paragraph(str(qty), s["table_cell_right"]),
            Paragraph(_fmt(rate), s["table_cell_right"]),
            Paragraph(_fmt(amount), s["table_cell_right"]),
        ])

    if not items_raw:
        tbl_data.append([
            Paragraph("No items", s["small"]), "", "", "", "", ""
        ])

    items_tbl = Table(tbl_data, colWidths=col_widths, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), BG_SURFACE),
        ("TEXTCOLOR", (0, 0), (-1, 0), GOLD),
        ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        # Body
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1, GOLD),
        # Alignment
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BG_DARK, BG_SURFACE]),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 5*mm))

    # ══════════════════════════════════════════════════════════════════════════
    # 5. TAX BREAKUP + TOTAL
    # ══════════════════════════════════════════════════════════════════════════
    
    sub_amt = float(order.get("subtotal", 0))
    ship_amt = float(order.get("shipping_cost", 0))
    tax_amt = float(order.get("tax_amount", 0))
    total = float(order.get("total_amount", 0))
    tax_rate = round((tax_amt / (sub_amt + ship_amt) * 100), 1) if (sub_amt + ship_amt) > 0 else 0
    gst = _calculate_gst_breakdown(order)

    summary_data = [
        ["Subtotal", _fmt(sub_amt)],
        [f"CGST ({tax_rate/2}%)", _fmt(gst["cgst"])],
        [f"SGST ({tax_rate/2}%)", _fmt(gst["sgst"])],
        ["Shipping", "FREE" if ship_amt == 0 else _fmt(ship_amt)],
    ]

    summary_col_w = (_W - 2*_MARGIN) * 0.28
    sum_tbl = Table(summary_data, colWidths=[summary_col_w, summary_col_w], hAlign="RIGHT")
    sum_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), TEXT_MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, BORDER),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 2*mm))

    # Total row
    total_data = [["TOTAL", _fmt(total)]]
    total_tbl = Table(total_data, colWidths=[summary_col_w, summary_col_w], hAlign="RIGHT")
    total_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOLD_DIM),
        ("TEXTCOLOR", (0, 0), (-1, -1), GOLD),
        ("FONTNAME", (0, 0), (-1, -1), _FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(total_tbl)

    # ══════════════════════════════════════════════════════════════════════════
    # 6. NOTES + FOOTER
    # ══════════════════════════════════════════════════════════════════════════
    
    story.append(Spacer(1, 12*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 4*mm))
    
    notes = order.get("notes")
    if notes:
        story.append(Paragraph("<b>Notes:</b>", s["section_title"]))
        story.append(Paragraph(notes, s["body_muted"]))
        story.append(Spacer(1, 4*mm))
    
    story.append(Paragraph(
        "Thank you for shopping with Luviio!<br/>"
        "This is a computer-generated invoice and does not require a signature.<br/>"
        "For any queries, contact support@luviio.in",
        s["footer"],
    ))

    # ══════════════════════════════════════════════════════════════════════════
    # BUILD PDF
    # ══════════════════════════════════════════════════════════════════════════
    
    try:
        doc.build(story)
    except Exception as exc:
        logger.error("PDF build failed | order=%s: %s", order_id, exc)
        raise RuntimeError(f"Invoice generation failed: {exc}") from exc

    pdf_bytes = buf.getvalue()
    logger.info(
        "Invoice PDF built | order=%s size=%dKB items=%d",
        order_id, len(pdf_bytes) // 1024, len(items_raw)
    )
    return pdf_bytes