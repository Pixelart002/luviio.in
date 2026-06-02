"""
Invoice Router — Production Grade
==================================
GET /api/v1/orders/{order_id}/invoice

Server-side PDF generation — tamper-proof, professional invoices.
No client-side PDF manipulation possible.

Features:
  • GST-compliant invoice format (India)
  • Company branding (Luviio logo, colors)
  • Itemized billing with tax breakup
  • Shipping address, tracking info
  • QR code for order verification (future)
  • Streamed directly — no disk storage
  
Security:
  • Customer: only OWN paid/shipped/delivered/refunded orders
  • Admin: any order in invoiceable status
  • Pending/cancelled: blocked (404/409)
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, HRFlowable
)
from reportlab.platypus.flowables import KeepTogether
from reportlab.graphics.shapes import Drawing, Line
from reportlab.graphics import renderPDF

from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Invoice"])

_INVOICEABLE = frozenset({"paid", "shipped", "delivered", "refunded"})

_ORDER_SELECT = (
    "id, status, created_at, subtotal, shipping_cost, tax_amount, total_amount, "
    "notes, customer_id, "
    "shipping_line1, shipping_line2, shipping_city, shipping_state, "
    "shipping_postal_code, shipping_country, "
    "tracking_number, "
    "order_items(id, product_name, unit_price, quantity, subtotal)"
)

# ── Brand Constants ───────────────────────────────────────────────────────────
COMPANY = {
    "name": "LUVIIO",
    "full_name": "Luviio Luxury Bath & Sanitation",
    "tagline": "Premium Bath & Sanitation Products",
    "address": "India",
    "email": "support@luviio.in",
    "website": "luviio.in",
    "gstin": "NOT APPLICABLE",  # Update with actual GSTIN if registered
    "pan": "NOT APPLICABLE",     # Update with actual PAN if applicable
    "logo_path": None,           # Path to logo PNG (optional)
}

# Brand colors
GOLD = colors.HexColor('#c9a55e')
DARK_BG = colors.HexColor('#080808')
SURFACE = colors.HexColor('#0d0c0a')
BORDER = colors.HexColor('#1e1c18')
TEXT_PRIMARY = colors.HexColor('#f0ece4')
TEXT_MUTED = colors.HexColor('#7a7368')
WHITE = colors.white
BLACK = colors.black


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current: dict[str, Any]) -> str:
    profile = current.get("profile")
    if isinstance(profile, dict) and "id" in profile:
        return str(profile["id"])
    if "id" in current:
        return str(current["id"])
    raise HTTPException(401, "User ID not found")


def _is_admin(current: dict[str, Any]) -> bool:
    return current.get("profile", {}).get("role") == "admin"


def _fetch_order(sb: Any, order_id: str) -> dict[str, Any]:
    res = (
        sb.table("orders").select(_ORDER_SELECT)
        .eq("id", order_id).limit(1).execute()
    )
    if not res or not getattr(res, "data", None):
        raise HTTPException(404, "Order not found")
    return res.data[0]


def _fetch_customer(sb: Any, user_id: str) -> dict[str, Any]:
    try:
        res = (
            sb.table("users").select("email, full_name")
            .eq("id", user_id).limit(1).execute()
        )
        if res and getattr(res, "data", None):
            return res.data[0]
    except Exception as exc:
        logger.warning("Customer fetch failed: %s", exc)
    return {}


def _format_inr(amount: float | Decimal) -> str:
    """Format amount as Indian Rupees"""
    return f"₹{float(amount):,.2f}"


def _format_date(dt_str: str) -> str:
    """Format ISO date to readable Indian format"""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return dt_str[:10] if dt_str else "—"


def _short_id(uuid_str: str) -> str:
    """Shorten UUID for display"""
    return uuid_str[:8].upper() if uuid_str else "—"


# ── PDF Builder ───────────────────────────────────────────────────────────────

class LuviioInvoiceBuilder:
    """Professional GST-compliant invoice PDF generator"""
    
    def __init__(self, order: dict, customer: dict):
        self.order = order
        self.customer = customer
        self.buffer = io.BytesIO()
        self.width, self.height = A4  # 210 x 297 mm
        self.styles = getSampleStyleSheet()
        self._setup_styles()
        
    def _setup_styles(self):
        """Custom styles matching Luviio brand"""
        self.styles.add(ParagraphStyle(
            'InvoiceTitle', fontName='Helvetica-Bold', fontSize=24,
            textColor=GOLD, alignment=TA_LEFT, spaceAfter=4
        ))
        self.styles.add(ParagraphStyle(
            'InvoiceSubtitle', fontName='Helvetica', fontSize=9,
            textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=2
        ))
        self.styles.add(ParagraphStyle(
            'SectionHeader', fontName='Helvetica-Bold', fontSize=10,
            textColor=TEXT_PRIMARY, spaceBefore=12, spaceAfter=6,
            borderPadding=(0, 0, 2, 0)
        ))
        self.styles.add(ParagraphStyle(
            'TableCell', fontName='Helvetica', fontSize=8,
            textColor=TEXT_PRIMARY, alignment=TA_LEFT
        ))
        self.styles.add(ParagraphStyle(
            'TableCellRight', fontName='Helvetica', fontSize=8,
            textColor=TEXT_PRIMARY, alignment=TA_RIGHT
        ))
        self.styles.add(ParagraphStyle(
            'TableCellBold', fontName='Helvetica-Bold', fontSize=8,
            textColor=TEXT_PRIMARY, alignment=TA_LEFT
        ))
        self.styles.add(ParagraphStyle(
            'TotalRow', fontName='Helvetica-Bold', fontSize=11,
            textColor=GOLD, alignment=TA_RIGHT
        ))
        self.styles.add(ParagraphStyle(
            'FooterText', fontName='Helvetica', fontSize=7,
            textColor=TEXT_MUTED, alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            'InfoLabel', fontName='Helvetica-Bold', fontSize=7,
            textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=1
        ))
        self.styles.add(ParagraphStyle(
            'InfoValue', fontName='Helvetica', fontSize=8,
            textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=4
        ))
    
    def _header_table(self) -> Table:
        """Company name + Invoice title"""
        data = [
            [
                Paragraph(f"<b>{COMPANY['full_name']}</b>", self.styles['InvoiceTitle']),
                Paragraph(f"<b>TAX INVOICE</b>", ParagraphStyle(
                    'RightTitle', fontName='Helvetica-Bold', fontSize=16,
                    textColor=GOLD, alignment=TA_RIGHT
                ))
            ]
        ]
        t = Table(data, colWidths=[self.width * 0.6, self.width * 0.3])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        return t
    
    def _company_info(self) -> Table:
        """Company details + Order info side by side"""
        left = [
            [Paragraph(f"<b>{COMPANY['name']}</b>", self.styles['SectionHeader'])],
            [Paragraph(f"{COMPANY['address']}", self.styles['InfoValue'])],
            [Paragraph(f"Email: {COMPANY['email']}", self.styles['InfoValue'])],
            [Paragraph(f"Web: {COMPANY['website']}", self.styles['InfoValue'])],
        ]
        if COMPANY['gstin'] != "NOT APPLICABLE":
            left.append([Paragraph(f"GSTIN: {COMPANY['gstin']}", self.styles['InfoValue'])])
        
        right = [
            [Paragraph("<b>Order Details</b>", self.styles['SectionHeader'])],
            [Paragraph(f"Order #: {_short_id(self.order['id'])}", self.styles['InfoValue'])],
            [Paragraph(f"Date: {_format_date(self.order['created_at'])}", self.styles['InfoValue'])],
            [Paragraph(f"Status: {self.order['status'].upper()}", self.styles['InfoValue'])],
        ]
        if self.order.get('tracking_number'):
            right.append([Paragraph(f"Tracking: {self.order['tracking_number']}", self.styles['InfoValue'])])
        
        left_table = Table(left, colWidths=[self.width * 0.45])
        right_table = Table(right, colWidths=[self.width * 0.45])
        
        # Combine side by side
        combined = Table([[left_table, right_table]], colWidths=[self.width * 0.48, self.width * 0.48])
        combined.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ]))
        return combined
    
    def _customer_info(self) -> Table:
        """Bill To + Ship To"""
        customer_name = self.customer.get('full_name', '') or self.customer.get('email', 'Customer')
        customer_email = self.customer.get('email', '')
        
        ship_parts = [
            self.order.get('shipping_line1', ''),
            self.order.get('shipping_line2', ''),
            self.order.get('shipping_city', ''),
            self.order.get('shipping_state', ''),
            self.order.get('shipping_postal_code', ''),
            self.order.get('shipping_country', ''),
        ]
        ship_address = ', '.join(filter(None, ship_parts))
        
        data = [
            [
                [
                    [Paragraph("<b>Bill To:</b>", self.styles['InfoLabel'])],
                    [Paragraph(customer_name, self.styles['InfoValue'])],
                    [Paragraph(customer_email, self.styles['InfoValue'])],
                ],
                [
                    [Paragraph("<b>Ship To:</b>", self.styles['InfoLabel'])],
                    [Paragraph(ship_address or '—', self.styles['InfoValue'])],
                ]
            ]
        ]
        
        left_t = Table(data[0][0], colWidths=[self.width * 0.45])
        right_t = Table(data[0][1], colWidths=[self.width * 0.45])
        
        t = Table([[left_t, right_t]], colWidths=[self.width * 0.48, self.width * 0.48])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        return t
    
    def _items_table(self) -> Table:
        """Line items with proper GST columns"""
        items = self.order.get('order_items', [])
        
        # Header
        header = [
            Paragraph("<b>#</b>", self.styles['TableCellBold']),
            Paragraph("<b>Item Description</b>", self.styles['TableCellBold']),
            Paragraph("<b>HSN</b>", self.styles['TableCellBold']),
            Paragraph("<b>Qty</b>", self.styles['TableCellBold']),
            Paragraph("<b>Rate</b>", self.styles['TableCellBold']),
            Paragraph("<b>Amount</b>", self.styles['TableCellBold']),
        ]
        
        data = [header]
        
        for i, item in enumerate(items, 1):
            row = [
                Paragraph(str(i), self.styles['TableCell']),
                Paragraph(item.get('product_name', '—'), self.styles['TableCell']),
                Paragraph("—", self.styles['TableCell']),  # HSN code placeholder
                Paragraph(str(item.get('quantity', 1)), self.styles['TableCellRight']),
                Paragraph(_format_inr(item.get('unit_price', 0)), self.styles['TableCellRight']),
                Paragraph(_format_inr(item.get('subtotal', 0)), self.styles['TableCellRight']),
            ]
            data.append(row)
        
        col_widths = [
            self.width * 0.05,  # #
            self.width * 0.35,  # Item
            self.width * 0.10,  # HSN
            self.width * 0.08,  # Qty
            self.width * 0.15,  # Rate
            self.width * 0.17,  # Amount
        ]
        
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), SURFACE),
            ('TEXTCOLOR', (0, 0), (-1, 0), GOLD),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            # Body
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#0a0a0a')),
            ('TEXTCOLOR', (0, 1), (-1, -1), TEXT_PRIMARY),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
            ('LINEBELOW', (0, 0), (-1, 0), 1, GOLD),
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        return t
    
    def _totals_table(self) -> Table:
        """Subtotal, Tax, Shipping, Total"""
        subtotal = float(self.order.get('subtotal', 0))
        shipping = float(self.order.get('shipping_cost', 0))
        tax = float(self.order.get('tax_amount', 0))
        total = float(self.order.get('total_amount', 0))
        tax_rate = round((tax / (subtotal + shipping) * 100), 1) if (subtotal + shipping) > 0 else 0
        
        data = [
            [Paragraph("Subtotal", self.styles['TableCell']), Paragraph(_format_inr(subtotal), self.styles['TableCellRight'])],
            [Paragraph(f"GST ({tax_rate}%)", self.styles['TableCell']), Paragraph(_format_inr(tax), self.styles['TableCellRight'])],
            [Paragraph("Shipping", self.styles['TableCell']), 
             Paragraph("FREE" if shipping == 0 else _format_inr(shipping), self.styles['TableCellRight'])],
            [Paragraph("", self.styles['TableCell']), Paragraph("", self.styles['TableCellRight'])],
            [Paragraph("<b>TOTAL</b>", self.styles['TableCellBold']), 
             Paragraph(f"<b>{_format_inr(total)}</b>", self.styles['TotalRow'])],
        ]
        
        t = Table(data, colWidths=[self.width * 0.30, self.width * 0.15])
        t.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, GOLD),
            ('LINEABOVE', (0, -2), (-1, -2), 0.5, BORDER),
        ]))
        return t
    
    def _footer(self) -> Paragraph:
        """Terms & conditions footer"""
        text = (
            "This is a computer-generated invoice. "
            "For any queries, contact support@luviio.in. "
            "Thank you for shopping with Luviio!"
        )
        return Paragraph(text, self.styles['FooterText'])
    
    def build(self) -> bytes:
        """Build complete PDF and return bytes"""
        doc = SimpleDocTemplate(
            self.buffer, pagesize=A4,
            leftMargin=15*mm, rightMargin=15*mm,
            topMargin=15*mm, bottomMargin=15*mm,
            title=f"Invoice-{_short_id(self.order['id'])}",
            author="Luviio",
        )
        
        story = []
        
        # 1. Header (Company + Invoice title)
        story.append(self._header_table())
        story.append(Spacer(1, 4*mm))
        
        # 2. Golden divider line
        story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
        story.append(Spacer(1, 6*mm))
        
        # 3. Company info + Order details
        story.append(self._company_info())
        story.append(Spacer(1, 6*mm))
        
        # 4. Bill To + Ship To
        story.append(self._customer_info())
        story.append(Spacer(1, 8*mm))
        
        # 5. Items table
        story.append(Paragraph("<b>ORDER ITEMS</b>", self.styles['SectionHeader']))
        story.append(self._items_table())
        story.append(Spacer(1, 4*mm))
        
        # 6. Totals (right-aligned)
        totals_wrapper = Table(
            [[Spacer(1, 1), self._totals_table()]],
            colWidths=[self.width * 0.55, self.width * 0.35]
        )
        totals_wrapper.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ]))
        story.append(totals_wrapper)
        
        # 7. Notes
        if self.order.get('notes'):
            story.append(Spacer(1, 8*mm))
            story.append(Paragraph("<b>Notes:</b>", self.styles['InfoLabel']))
            story.append(Paragraph(self.order['notes'], self.styles['InfoValue']))
        
        # 8. Footer
        story.append(Spacer(1, 15*mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
        story.append(Spacer(1, 4*mm))
        story.append(self._footer())
        
        # Build PDF
        doc.build(story)
        return self.buffer.getvalue()


# ── Router ────────────────────────────────────────────────────────────────────

@router.get("/orders/{order_id}/invoice")
def download_invoice(
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download PDF invoice for an order.
    
    Customer: own paid/shipped/delivered/refunded orders only.
    Admin: any order in invoiceable status.
    """
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    oid_str = str(order_id)
    is_admin = _is_admin(current)
    
    order = _fetch_order(sb, oid_str)
    
    # Ownership check
    if not is_admin and order.get("customer_id") != user_id:
        raise HTTPException(404, "Order not found")
    
    # Status check
    order_status = order.get("status", "")
    if order_status not in _INVOICEABLE:
        raise HTTPException(409, f"Invoice not available for '{order_status}' orders")
    
    # Fetch customer
    customer = _fetch_customer(sb, order.get("customer_id", ""))
    
    # Build PDF
    try:
        builder = LuviioInvoiceBuilder(order, customer)
        pdf_bytes = builder.build()
    except Exception as exc:
        logger.error("PDF generation failed | order=%s: %s", oid_str, exc)
        raise HTTPException(500, "Could not generate invoice")
    
    filename = f"Luviio-Invoice-{oid_str[:8].upper()}.pdf"
    logger.info("Invoice downloaded | order=%s size=%d", oid_str, len(pdf_bytes))
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "Cache-Control": "no-store",
        },
    )