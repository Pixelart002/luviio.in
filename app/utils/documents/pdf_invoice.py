"""
PDF Invoice Generator — Amazon Style Enterprise Grade
=====================================================
Path: app/utils/documents/pdf_invoice.py

Generates a professional, Amazon-style Tax Invoice.
- Uses strict 2x2 Address & Metadata Grid (Billing/Shipping on Left, Seller/Order on Right).
- Reads SSOT pricing strictly from the DB payload (zero hardcoded math).
- Fixes the Rupee (₹) symbol crash issue by safely using 'Rs.'
"""
import io
import datetime
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
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
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=14, spaceAfter=5)
    normal_style = styles['Normal']
    normal_style.leading = 14  # Better line spacing
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

    # ─── 2. 2x2 GRID (Billing/Shipping on Left, Seller/Order on Right) ───
    customer_name = customer.get("full_name") or order.get("customer_name") or "Valued Customer"
    customer_email = customer.get("email") or ""
    
    shipping_addr = (
        f"{order.get('shipping_line1', '')}<br/>"
        f"{order.get('shipping_city', '')}, {order.get('shipping_state', '')} {order.get('shipping_postal_code', '')}<br/>"
        f"{order.get('shipping_country', 'IN')}"
    )

    order_id = str(order.get("id", "N/A"))[:8].upper()
    order_date = str(order.get("created_at", "N/A"))[:10]
    invoice_date = datetime.datetime.now().strftime("%Y-%m-%d")

    # [Row 1, Col 1] Billing Address
    billing_info = f"""<b>Billing Address:</b><br/>
{customer_name}<br/>
{customer_email}"""

    # [Row 1, Col 2] Seller Info
    seller_info = """<b>Sold By:</b><br/>
LUVIIO E-Commerce Pvt. Ltd.<br/>
New Delhi, India<br/>
GSTIN: 07AAACA1234A1Z5"""

    # [Row 2, Col 1] Shipping Address
    shipping_info = f"""<b>Shipping Address:</b><br/>
{customer_name}<br/>
{shipping_addr}"""

    # [Row 2, Col 2] Order Info
    order_info = f"""<b>Order Number:</b> {order_id}<br/>
<b>Order Date:</b> {order_date}<br/>
<b>Invoice Date:</b> {invoice_date}"""

    # Constructing the 2x2 Table
    header_table_data = [
        [Paragraph(billing_info, normal_style), Paragraph(seller_info, normal_style)],
        [Paragraph(shipping_info, normal_style), Paragraph(order_info, normal_style)]
    ]
    
    header_table = Table(header_table_data, colWidths=[260, 260])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey), # Amazon style grid boxes
        ('PADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 20))

    # ─── 3. ITEMS TABLE (Amazon Format) ───
    table_data = [
        ['Sl. No', 'Description', 'Unit Price', 'Qty', 'Net Amount']
    ]

    items = order.get("order_items", [])
    if not items:
        items = order.get("items", [])

    for idx, item in enumerate(items, start=1):
        prod_name = item.get("product_name") or item.get("product_slug") or "Product Item"
        qty = item.get("quantity", 1)
        
        # Pulling prices strictly from the DB payload (SSOT)
        unit_price = float(item.get("unit_price", 0))
        net_amt = float(item.get("subtotal", unit_price * qty))
        
        table_data.append([
            str(idx),
            Paragraph(prod_name, normal_style),
            format_currency(unit_price),
            str(qty),
            format_currency(net_amt)
        ])

    table = Table(table_data, colWidths=[40, 240, 80, 40, 120])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f4f4f4")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        
        # Data Alignments
        ('ALIGN', (0, 1), (0, -1), 'CENTER'), # Sl. No
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),   # Desc
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'), # Prices & Qty
        
        # Borders
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 15))

    # ─── 4. TOTALS CALCULATIONS (Strictly from SSOT DB Payload) ───
    # The pricing engine has already computed these, we just extract them
    subtotal = float(order.get("subtotal", 0))
    shipping = float(order.get("shipping_cost", 0))
    tax = float(order.get("tax_amount", 0))
    total = float(order.get("total_amount", 0))

    totals_data = [
        ["Subtotal:", format_currency(subtotal)],
        ["Shipping Charges:", format_currency(shipping)],
        ["Estimated Tax (IGST/CGST/SGST):", format_currency(tax)],
        ["Grand Total:", format_currency(total)]
    ]

    totals_table = Table(totals_data, colWidths=[380, 140])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, -1), (1, -1), 'Helvetica-Bold'), # Bold Grand Total row
        ('LINEABOVE', (0, -1), (1, -1), 1, colors.black), # Line above Grand Total
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(totals_table)
    elements.append(Spacer(1, 40))

    # ─── 5. FOOTER & SIGNATURE ───
    elements.append(Paragraph("<b>Authorized Signatory</b>", right_style))
    elements.append(Paragraph("LUVIIO E-Commerce", right_style))
    elements.append(Spacer(1, 30))
    
    footer_text = "<font color='grey'><i>This is a computer generated invoice and does not require a physical signature.</i></font>"
    elements.append(Paragraph(footer_text, ParagraphStyle('Small', parent=normal_style, alignment=TA_CENTER, fontSize=8)))

    # Build the actual PDF
    doc.build(elements)
    
    return buffer.getvalue()