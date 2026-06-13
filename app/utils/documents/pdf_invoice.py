"""
PDF Invoice Builder — reportlab
================================
Architecture Layer: Utils (Facade Pattern)
Path: app/utils/documents/pdf_invoice.py
"""
from __future__ import annotations
import io
import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from html import escape 

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

logger = logging.getLogger(__name__)

# ── Font Setup for Rupee (₹) Support ──────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_DIR, "fonts")

_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_CURRENCY_SYMBOL = "₹ "  # Defaulting to Rupee symbol

try:
    # Font files must be physically present in app/utils/documents/fonts/
    pdfmetrics.registerFont(TTFont("Roboto", os.path.join(_FONT_DIR, "Roboto-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Roboto-Bold", os.path.join(_FONT_DIR, "Roboto-Bold.ttf")))
    registerFontFamily("Roboto", normal="Roboto", bold="Roboto-Bold")
    _FONT_REGULAR = "Roboto"
    _FONT_BOLD = "Roboto-Bold"
    logger.info("Custom fonts loaded for Rupee symbol support")
except Exception as e:
    _CURRENCY_SYMBOL = "Rs. "  # Safer fallback for standard Helvetica
    logger.warning(f"Custom fonts failed — falling back to Helvetica. Using 'Rs.' instead of '₹': {e}")

# ── Brand Colors (Premium Light Theme for Print/PDF) ──────────────────────────
# FIX: Changed to Light Theme so text is visible on white PDF background
BG_DARK    = colors.HexColor("#F9F8F6")  # Very Light Warm Gray (Table headers)
BG_SURFACE = colors.HexColor("#FFFFFF")  # Pure White
GOLD       = colors.HexColor("#c9a55e")  # Luviio Brand Gold
GOLD_DIM   = colors.HexColor("#FDF8F0")  # Very light gold for total background
TEXT       = colors.HexColor("#1A1A1A")  # Almost Black (High visibility)
TEXT_MUTED = colors.HexColor("#666666")  # Dark Gray for subtitles
BORDER     = colors.HexColor("#EAEAEA")  # Light gray borders
WHITE      = colors.white

_W, _H  = A4
_MARGIN = 18 * mm

def _styles() -> dict[str, ParagraphStyle]:
    return {
        "brand": ParagraphStyle("brand", fontSize=28, leading=32, textColor=GOLD, fontName=_FONT_BOLD, letterSpacing=4, alignment=TA_LEFT),
        "brand_sub": ParagraphStyle("brand_sub", fontSize=8, leading=10, textColor=TEXT_MUTED, fontName=_FONT_REGULAR, alignment=TA_LEFT),
        "invoice_title": ParagraphStyle("invoice_title", fontSize=16, leading=20, textColor=TEXT, fontName=_FONT_BOLD, alignment=TA_RIGHT),
        "section_title": ParagraphStyle("section_title", fontSize=10, leading=14, textColor=GOLD, fontName=_FONT_BOLD, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontSize=9, leading=13, textColor=TEXT, fontName=_FONT_REGULAR),
        "body_muted": ParagraphStyle("body_muted", fontSize=9, leading=13, textColor=TEXT_MUTED, fontName=_FONT_REGULAR),
        "small": ParagraphStyle("small", fontSize=8, leading=11, textColor=TEXT_MUTED, fontName=_FONT_REGULAR),
        "footer": ParagraphStyle("footer", fontSize=8, leading=11, textColor=TEXT_MUTED, fontName=_FONT_REGULAR, alignment=TA_CENTER),
        "table_header": ParagraphStyle("table_header", fontSize=9, leading=12, textColor=TEXT, fontName=_FONT_BOLD),
        # Paragraph handles text wrapping automatically for descriptions
        "table_cell": ParagraphStyle("table_cell", fontSize=9, leading=12, textColor=TEXT, fontName=_FONT_REGULAR),
        "table_cell_right": ParagraphStyle("table_cell_right", fontSize=9, leading=12, textColor=TEXT, fontName=_FONT_REGULAR, alignment=TA_RIGHT),
        "total_label": ParagraphStyle("total_label", fontSize=11, leading=15, textColor=TEXT, fontName=_FONT_BOLD),
        "total_value": ParagraphStyle("total_value", fontSize=13, leading=17, textColor=GOLD, fontName=_FONT_BOLD, alignment=TA_RIGHT),
    }

def _esc(text: Any) -> str: 
    return escape(str(text)) if text else ""

def _fmt(amount: Any, symbol: str = None) -> str:
    sym = symbol if symbol is not None else _CURRENCY_SYMBOL
    try: 
        return f"{sym}{float(amount):,.2f}"
    except (TypeError, ValueError): 
        return f"{sym}0.00"

def _short_id(uuid_str: str) -> str: 
    return str(uuid_str)[:8].upper() if uuid_str else "—"

def _addr_block(order: dict[str, Any]) -> str:
    parts = [
        _esc(order.get("shipping_line1")), 
        _esc(order.get("shipping_line2")), 
        _esc(order.get("shipping_city")), 
        _esc(order.get("shipping_state")), 
        _esc(order.get("shipping_postal_code")), 
        _esc(order.get("shipping_country"))
    ]
    return "<br/>".join(p for p in parts if p)

def _calculate_gst_breakdown(order: dict[str, Any]) -> dict[str, float]:
    tax_total = float(order.get("tax_amount", 0) or 0)
    return {"cgst": round(tax_total / 2, 2), "sgst": round(tax_total / 2, 2), "total": tax_total}

def build_invoice_pdf(order: dict[str, Any], customer: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, 
        leftMargin=_MARGIN, rightMargin=_MARGIN, 
        topMargin=_MARGIN, bottomMargin=_MARGIN, 
        title=f"Invoice-{_short_id(order.get('id', ''))}", 
        author="Luviio"
    )
    s = _styles()
    story = []

    order_id   = str(order.get("id", ""))
    invoice_no = f"INV-{_short_id(order_id)}"
    try:
        dt = datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00"))
        date_str = dt.strftime("%d %B %Y, %I:%M %p")
    except Exception:
        date_str = datetime.now(timezone.utc).strftime("%d %B %Y")

    customer_name = _esc(customer.get("full_name") or "Customer")
    customer_email = _esc(customer.get("email", ""))
    ship_addr = _addr_block(order)
    status = _esc(str(order.get("status", "")).upper())
    tracking = _esc(order.get("tracking_number", ""))

    # --- Header ---
    header_tbl = Table([
        [Paragraph("LUVIIO", s["brand"]), Paragraph("<b>TAX INVOICE</b>", s["invoice_title"])],
        [Paragraph("Premium Bath & Sanitation Products", s["brand_sub"]), Paragraph(invoice_no, s["body_muted"])]
    ], colWidths=[(_W - 2*_MARGIN)*0.55, (_W - 2*_MARGIN)*0.45])
    header_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(header_tbl)
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD))
    story.append(Spacer(1, 6*mm))

    # --- Company & Order Details ---
    col_w = (_W - 2*_MARGIN) / 2
    company_info = Table([[
        Table([
            [Paragraph("<b>From:</b>", s["section_title"])], 
            [Paragraph("Luviio Luxury Bath & Sanitation<br/>India<br/>support@luviio.in<br/>luviio.in", s["body_muted"])]
        ], colWidths=[col_w - 4*mm]),
        Table([
            [Paragraph("<b>Order Details</b>", s["section_title"])], 
            [Paragraph(f"<b>Invoice No:</b> {invoice_no}<br/><b>Order ID:</b> #{_short_id(order_id)}<br/><b>Date:</b> {date_str}<br/><b>Status:</b> {status}", s["body_muted"])]
        ], colWidths=[col_w - 4*mm]),
    ]], colWidths=[col_w, col_w])
    company_info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(company_info)
    story.append(Spacer(1, 5*mm))

    # --- Bill To & Ship To ---
    bill_ship = Table([[
        Table([
            [Paragraph("<b>Bill To:</b>", s["section_title"])], 
            [Paragraph(f"{customer_name}<br/>{customer_email}", s["body_muted"])]
        ], colWidths=[col_w - 4*mm]),
        Table([
            [Paragraph("<b>Ship To:</b>", s["section_title"])], 
            [Paragraph(ship_addr or "—", s["body_muted"])]
        ], colWidths=[col_w - 4*mm]),
    ]], colWidths=[col_w, col_w])
    bill_ship.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(bill_ship)
    story.append(Spacer(1, 6*mm))
    
    if tracking:
        story.append(Paragraph(f"<b>Tracking:</b> {tracking}", s["body_muted"]))
        story.append(Spacer(1, 3*mm))

    # --- Items Table ---
    story.append(Paragraph("<b>ORDER ITEMS</b>", s["section_title"]))
    story.append(Spacer(1, 3*mm))

    items_raw = order.get("order_items") or []
    # Adjusted column widths to give more space to the description so it wraps nicely
    col_widths = [
        (_W - 2*_MARGIN)*0.08,  # #
        (_W - 2*_MARGIN)*0.40,  # Description
        (_W - 2*_MARGIN)*0.10,  # Qty
        (_W - 2*_MARGIN)*0.20,  # Rate
        (_W - 2*_MARGIN)*0.22   # Amount
    ]

    tbl_data = [[
        Paragraph("<b>#</b>", s["table_header"]), 
        Paragraph("<b>Description</b>", s["table_header"]), 
        Paragraph("<b>Qty</b>", s["table_header"]), 
        Paragraph("<b>Rate</b>", s["table_header"]), 
        Paragraph("<b>Amount</b>", s["table_header"])
    ]]

    for i, item in enumerate(items_raw, 1):
        rate = float(item.get("unit_price", 0) or 0)
        qty = int(item.get("quantity", 0) or 0)
        subtotal = float(item.get("subtotal", rate * qty) or 0)
        
        tbl_data.append([
            Paragraph(str(i), s["table_cell"]), 
            Paragraph(_esc(item.get("product_name") or "—"), s["table_cell"]), 
            Paragraph(str(qty), s["table_cell_right"]), 
            Paragraph(_fmt(rate), s["table_cell_right"]), 
            Paragraph(_fmt(subtotal), s["table_cell_right"])
        ])

    if not items_raw: 
        tbl_data.append([Paragraph("No items", s["small"]), "", "", "", ""])

    items_tbl = Table(tbl_data, colWidths=col_widths, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BG_DARK), 
        ("TEXTCOLOR", (0, 0), (-1, 0), TEXT), 
        ("TOPPADDING", (0, 0), (-1, -1), 8), 
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8), 
        ("LEFTPADDING", (0, 0), (-1, -1), 5), 
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER), 
        ("ALIGN", (0, 0), (0, -1), "CENTER"), 
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"), 
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BG_SURFACE, BG_DARK]),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 5*mm))

    # --- Summary ---
    sub_amt  = float(order.get("subtotal", 0) or 0)
    ship_amt = float(order.get("shipping_cost", 0) or 0)
    tax_amt  = float(order.get("tax_amount", 0) or 0)
    total    = float(order.get("total_amount", 0) or 0)
    gst      = _calculate_gst_breakdown(order)
    tax_rate = round((tax_amt / (sub_amt + ship_amt) * 100), 1) if (sub_amt + ship_amt) > 0 else 0

    summary_col_w = (_W - 2*_MARGIN) * 0.35
    sum_tbl = Table([
        ["Subtotal", _fmt(sub_amt)], 
        [f"CGST ({tax_rate/2}%)", _fmt(gst["cgst"])], 
        [f"SGST ({tax_rate/2}%)", _fmt(gst["sgst"])], 
        ["Shipping", "FREE" if ship_amt == 0 else _fmt(ship_amt)]
    ], colWidths=[summary_col_w, summary_col_w], hAlign="RIGHT")
    
    sum_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9), 
        ("TEXTCOLOR", (0, 0), (0, -1), TEXT_MUTED), 
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT), 
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), 
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4), 
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, BORDER),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 2*mm))

    total_tbl = Table([["TOTAL", _fmt(total)]], colWidths=[summary_col_w, summary_col_w], hAlign="RIGHT")
    total_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOLD_DIM), 
        ("TEXTCOLOR", (0, 0), (-1, -1), GOLD), 
        ("FONTNAME", (0, 0), (-1, -1), _FONT_BOLD), 
        ("FONTSIZE", (0, 0), (-1, -1), 13),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"), 
        ("TOPPADDING", (0, 0), (-1, -1), 10), 
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10), 
        ("LEFTPADDING", (0, 0), (-1, -1), 10), 
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(total_tbl)

    story.append(Spacer(1, 15*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 4*mm))
    
    if order.get("notes"):
        story.append(Paragraph("<b>Notes:</b>", s["section_title"]))
        story.append(Paragraph(_esc(order.get("notes")), s["body_muted"]))
        story.append(Spacer(1, 4*mm))
    
    story.append(Paragraph("Thank you for shopping with Luviio!<br/>This is a computer-generated invoice and does not require a physical signature.<br/>For any queries, please contact support@luviio.in", s["footer"]))

    try: 
        doc.build(story)
    except Exception as exc: 
        raise RuntimeError(f"Invoice generation failed: {exc}") from exc

    return buf.getvalue()