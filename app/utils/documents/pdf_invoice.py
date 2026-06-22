"""
PDF Invoice Generator — Amazon Style (Crash-Proof)
==================================================
Path: app/utils/documents/pdf_invoice.py

Generates a professional, Amazon-style Tax Invoice.
Fixes the Rupee (₹) symbol crash issue by safely using 'Rs.'
"""
import io
import datetime
from decimal import Decimal
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

def format_currency(amount: Any) -> str:
    """
    Intelligently handles currency formatting.
    NOTE: Default ReportLab fonts (Helvetica) DO NOT support the '₹' symbol.
    Using '₹' will cause a UnicodeDecodeError or render a black box.
    We use 'Rs.' for 100% crash-proof cross-platform rendering.
    """
    if amount is None:
        return "Rs. 0.00"
    try:
        val = float(amount)
        return f"Rs. {val:,.2f}"
    except (ValueError, TypeError):
        return "Rs. 0.00"

def build_invoice_pdf(order: dict[str, Any], customer: dict[str, Any]) -> bytes:
    """
    Builds an Amazon-style PDF invoice strictly in-memory.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30
    )

    styles = getSampleStyleSheet()
    
    # Custom Paragraph Styles
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=16, spaceAfter=10)
    normal_style = styles['Normal']
    bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontName='Helvetica-Bold')
    right_style = ParagraphStyle('Right', parent=styles['Normal'], alignment=TA_RIGHT)

    elements = []

    # ─── 1. HEADER (Status dependent title) ───
    status = order.get("status", "").lower()
    if status == "refunded":
        doc_title = "REFUND / CREDIT NOTE"
    else:
        doc_title = "TAX INVOICE / BILL OF SUPPLY"

    elements.append(Paragraph(f"<b>{doc_title}</b>", title_style))
    elements.append(Paragraph("Original for Recipient", right_style))
    elements.append(Spacer(1, 10))

    # ─── 2. SELLER & BUYER DETAILS (Side by Side) ───
    customer_name = customer.get("full_name") or order.get("customer_name") or "Valued Customer"
    customer_email = customer.get("email") or ""
    
    shipping_addr = (
        f"{order.get('shipping_line1', '')}<br/>"
        f"{order.get('shipping_city', '')}, {order.get('shipping_postal_code', '')}<br/>"
        f"{order.get('shipping_country', 'India')}"
    )

    # Amazon style boxed layout
    seller_info = """<b>Sold By:</b><br/>
LUVIIO E-Commerce Pvt. Ltd.<br/>
New Delhi, India<br/>
GSTIN: 07AAACA1234A1Z5
"""

    billing_info = f"""<b>Billing & Shipping Address:</b><br/>
<b>{customer_name}</b><br/>
{shipping_addr}<br/>
{customer_email}
"""

    header_table_data = [[Paragraph(seller_info, normal_style), Paragraph(billing_info, normal_style)]]
    header_table = Table(header_table_data, colWidths=[260, 260])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (0, 0), 0.5, colors.grey),
        ('BOX', (1, 0), (1, 0), 0.5, colors.grey),
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 15))

    # ─── 3. ORDER METADATA ───
    order_id = str(order.get("id", "N/A"))[:8].upper()
    order_date = str(order.get("created_at", "N/A"))[:10]
    invoice_date = datetime.datetime.now().strftime("%Y-%m-%d")

    meta_text = (
        f"<b>Order Number:</b> {order_id} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; "
        f"<b>Order Date:</b> {order_date} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; "
        f"<b>Invoice Date:</b> {invoice_date}"
    )
    elements.append(Paragraph(meta_text, normal_style))
    elements.append(Spacer(1, 15))

    # ─── 4. ITEMS TABLE (Amazon Format) ───
    table_data = [
        ['Sl.', 'Description', 'Unit Price', 'Qty', 'Net Amount']
    ]

    items = order.get("order_items", [])
    if not items:
        # Fallback if nested items are not fetched properly
        items = order.get("items", [])

    for idx, item in enumerate(items, start=1):
        # Extract product name safely depending on how your DB returns it
        prod_name = item.get("product_name") or item.get("product_slug") or "Product Item"
        qty = item.get("quantity", 1)
        unit_price = float(item.get("unit_price", 0))
        net_amt = unit_price * qty
        
        table_data.append([
            str(idx),
            Paragraph(prod_name, normal_style),
            format_currency(unit_price),
            str(qty),
            format_currency(net_amt)
        ])

    table = Table(table_data, colWidths=[30, 240, 90, 40, 120])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        
        # Data Alignments
        ('ALIGN', (0, 1), (0, -1), 'CENTER'), # Sl.
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),   # Desc
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'), # Prices & Qty
        
        # Borders
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 15))

    # ─── 5. TOTALS CALCULATIONS ───
    subtotal = float(order.get("subtotal", 0))
    shipping = float(order.get("shipping_cost", 0))
    tax = float(order.get("tax_amount", 0))
    total = float(order.get("total_amount", 0))

    totals_data = [
        ["Subtotal:", format_currency(subtotal)],
        ["Shipping Charges:", format_currency(shipping)],
        ["Estimated Tax:", format_currency(tax)],
        ["Grand Total:", format_currency(total)]
    ]

    totals_table = Table(totals_data, colWidths=[380, 140])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (1, -1), 'Helvetica-Bold'), # Bold Grand Total
        ('LINEABOVE', (0, -1), (1, -1), 1, colors.black), # Line above Grand Total
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    
    elements.append(totals_table)
    elements.append(Spacer(1, 40))

    # ─── 6. FOOTER & SIGNATURE ───
    elements.append(Paragraph("<b>Authorized Signatory</b>", right_style))
    elements.append(Paragraph("LUVIIO E-Commerce", right_style))
    elements.append(Spacer(1, 20))
    
    footer_text = "<font color='grey'><i>This is a computer generated invoice and does not require a physical signature.</i></font>"
    elements.append(Paragraph(footer_text, ParagraphStyle('Small', parent=normal_style, alignment=TA_CENTER, fontSize=8)))

    # Build the actual PDF
    doc.build(elements)
    
    return buffer.getvalue()