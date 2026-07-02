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
    Using '₹' will cause a UnicodeDecodeError. We use 'Rs.' for 100% safety.
    """
    if amount is None:
        return "Rs. 0.00"
    try:
        val = float(amount)
        return f"Rs. {val:,.2f}"
    except (ValueError, TypeError):
        return "Rs. 0.00"

def number_to_words(n: float) -> str:
    """Basic helper to convert total to words (Simplified for invoice)."""
    try:
        n = int(n)
        return f"Rupees {n} Only" # For a full production app, use num2words library
    except Exception:
        return ""

def build_invoice_pdf(order: dict[str, Any], customer: dict[str, Any]) -> bytes:
    """
    Builds an exact Amazon-style PDF invoice strictly in-memory.
    """
    buffer = io.BytesIO()
    # Amazon uses tight margins to fit massive tables
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=20, leftMargin=20, topMargin=25, bottomMargin=25
    )

    styles = getSampleStyleSheet()
    
    # ─── AMAZON SPECIFIC TYPOGRAPHY ───
    amazon_normal = ParagraphStyle('AmzNormal', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10)
    amazon_bold = ParagraphStyle('AmzBold', parent=amazon_normal, fontName='Helvetica-Bold')
    amazon_title = ParagraphStyle('AmzTitle', parent=styles['Heading1'], alignment=TA_RIGHT, fontName='Helvetica-Bold', fontSize=12, leading=14)
    amazon_small = ParagraphStyle('AmzSmall', parent=amazon_normal, fontSize=7, leading=9)
    amazon_right = ParagraphStyle('AmzRight', parent=amazon_normal, alignment=TA_RIGHT)
    amazon_center = ParagraphStyle('AmzCenter', parent=amazon_normal, alignment=TA_CENTER)

    elements = []

    # ─── 1. HEADER ROW (Logo & Invoice Title) ───
    status = order.get("status", "").lower()
    doc_title = "Refund / Credit Note" if status == "refunded" else "Tax Invoice/Bill of Supply/Cash Memo"
    
    header_data = [
        [
            Paragraph("<b>LUVIIO INDIA</b><br/><i>Premium E-Commerce</i>", ParagraphStyle('Logo', parent=amazon_bold, fontSize=16)),
            Paragraph(f"<b>{doc_title}</b><br/>(Original for Recipient)", amazon_title)
        ]
    ]
    t_header = Table(header_data, colWidths=[270, 270])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(t_header)

    # ─── 2. ADDRESS BLOCK (3 Columns: Seller, Billing, Shipping) ───
    customer_name = customer.get("full_name") or order.get("customer_name") or "Valued Customer"
    
    shipping_addr = (
        f"{order.get('shipping_line1', '')}<br/>"
        f"{order.get('shipping_line2', '') + '<br/>' if order.get('shipping_line2') else ''}"
        f"{order.get('shipping_city', '')}, {order.get('shipping_state', '')} {order.get('shipping_postal_code', '')}<br/>"
        f"{order.get('shipping_country', 'IN')}"
    )

    seller_info = """<b>Sold By:</b><br/>
LUVIIO E-Commerce Private Limited<br/>
Ground Floor, Cyber Hub Building,<br/>
Gurugram, Haryana, 122002<br/>
IN<br/><br/>
<b>PAN No:</b> ABCDE1234F<br/>
<b>GST Registration No:</b> 06ABCDE1234F1Z5
"""

    billing_info = f"""<b>Billing Address:</b><br/>
{customer_name}<br/>
{shipping_addr}<br/><br/>
<b>State/UT Code:</b> 06
"""

    shipping_info = f"""<b>Shipping Address:</b><br/>
{customer_name}<br/>
{shipping_addr}<br/><br/>
<b>State/UT Code:</b> 06<br/>
<b>Place of supply:</b> {order.get('shipping_city', 'Haryana')}
"""

    addr_data = [[
        Paragraph(seller_info, amazon_normal),
        Paragraph(billing_info, amazon_normal),
        Paragraph(shipping_info, amazon_normal)
    ]]
    t_addr = Table(addr_data, colWidths=[180, 180, 180])
    t_addr.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t_addr)

    # ─── 3. ORDER METADATA BAR ───
    order_id = str(order.get("id", "N/A"))[:8].upper()
    order_date = str(order.get("created_at", "N/A"))[:10]
    invoice_date = datetime.datetime.now().strftime("%d.%m.%Y")
    invoice_num = f"IN-{datetime.datetime.now().strftime('%Y%m')}-{order_id}"

    meta_data = [
        [
            Paragraph(f"<b>Order Number:</b> {order_id}<br/><b>Order Date:</b> {order_date}", amazon_normal),
            Paragraph(f"<b>Invoice Number:</b> {invoice_num}<br/><b>Invoice Details:</b> IN-DEL-{order_id}<br/><b>Invoice Date:</b> {invoice_date}", amazon_normal)
        ]
    ]
    t_meta = Table(meta_data, colWidths=[270, 270])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t_meta)

    # ─── 4. MAIN ITEMS TABLE (Amazon 9-Column Grid) ───
    # Sl | Description | Unit Price | Qty | Net Amt | Tax Rate | Tax Type | Tax Amt | Total Amt
    table_data = [[
        Paragraph("<b>Sl. No</b>", amazon_center),
        Paragraph("<b>Description</b>", amazon_center),
        Paragraph("<b>Unit Price</b>", amazon_center),
        Paragraph("<b>Qty</b>", amazon_center),
        Paragraph("<b>Net Amount</b>", amazon_center),
        Paragraph("<b>Tax Rate</b>", amazon_center),
        Paragraph("<b>Tax Type</b>", amazon_center),
        Paragraph("<b>Tax Amount</b>", amazon_center),
        Paragraph("<b>Total Amount</b>", amazon_center)
    ]]

    items = order.get("order_items", []) or order.get("items", [])
    
    total_tax_overall = 0.0
    total_net_overall = 0.0
    tax_rate = order.get("tax_rate_pct", 18.0) # Assuming 18% standard IGST for simplicity

    for idx, item in enumerate(items, start=1):
        prod_name = item.get("product_name") or item.get("product_slug") or "Premium Bath Fitting"
        qty = int(item.get("quantity", 1))
        unit_price = float(item.get("unit_price", 0))
        net_amt = unit_price * qty
        
        # Amazon calculates tax per item. We approximate it based on line subtotal.
        item_tax = float(item.get("subtotal", net_amt)) * (tax_rate / 100)
        item_total = net_amt + item_tax

        total_net_overall += net_amt
        total_tax_overall += item_tax

        table_data.append([
            Paragraph(str(idx), amazon_center),
            Paragraph(f"<b>{prod_name}</b><br/>HSN: 84818020", amazon_normal),
            Paragraph(format_currency(unit_price), amazon_right),
            Paragraph(str(qty), amazon_center),
            Paragraph(format_currency(net_amt), amazon_right),
            Paragraph(f"{tax_rate}%", amazon_center),
            Paragraph("IGST", amazon_center),
            Paragraph(format_currency(item_tax), amazon_right),
            Paragraph(format_currency(item_total), amazon_right)
        ])

    # Add Shipping Row if applicable
    shipping = float(order.get("shipping_cost", 0))
    if shipping > 0:
        table_data.append([
            Paragraph("-", amazon_center),
            Paragraph("<b>Shipping Charges</b>", amazon_normal),
            Paragraph(format_currency(shipping), amazon_right),
            Paragraph("1", amazon_center),
            Paragraph(format_currency(shipping), amazon_right),
            Paragraph("18%", amazon_center),
            Paragraph("IGST", amazon_center),
            Paragraph(format_currency(shipping * 0.18), amazon_right),
            Paragraph(format_currency(shipping * 1.18), amazon_right)
        ])
        total_net_overall += shipping
        total_tax_overall += (shipping * 0.18)

    # Totals Row inside the grid
    grand_total_db = float(order.get("total_amount", total_net_overall + total_tax_overall))
    
    table_data.append([
        "", 
        Paragraph("<b>TOTAL:</b>", amazon_bold), 
        "", 
        "", 
        Paragraph(f"<b>{format_currency(total_net_overall)}</b>", amazon_right), 
        "", 
        "", 
        Paragraph(f"<b>{format_currency(total_tax_overall)}</b>", amazon_right), 
        Paragraph(f"<b>{format_currency(grand_total_db)}</b>", amazon_right)
    ])

    # Col Widths: Total 540 max
    t_items = Table(table_data, colWidths=[25, 140, 55, 25, 65, 45, 45, 65, 75])
    t_items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e6e6e6")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('INNERGRID', (0, 0), (-1, -2), 0.5, colors.black), # Inner grid for items
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black), # Thick line before total
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_items)
    
    # ─── 5. AMOUNT IN WORDS & SIGNATURE ───
    amt_words = number_to_words(grand_total_db)
    
    sig_data = [
        [
            Paragraph(f"<b>Amount in Words:</b><br/>{amt_words}<br/><br/><i>Whether tax is payable on reverse charge - No</i>", amazon_normal),
            Paragraph("<b>For LUVIIO E-Commerce Pvt. Ltd:</b><br/><br/><br/>Authorized Signatory", amazon_right)
        ]
    ]
    t_sig = Table(sig_data, colWidths=[270, 270])
    t_sig.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t_sig)
    elements.append(Spacer(1, 20))

    # ─── 6. AMAZON FOOTER NOTES ───
    footer_notes = """
* ASSPL-Amazon Seller Services Pvt. Ltd., ARCS-Amazon Retail Computing Services, BKC-Building Kapil Centre.<br/>
* This is a computer generated invoice and does not require a physical signature.<br/>
* Returns policy: Please visit luviio.in/returns for detailed return policies.<br/>
* To contact us regarding your order, please email support@luviio.in.
"""
    elements.append(Paragraph(footer_notes, amazon_small))

    # Build PDF
    doc.build(elements)
    
    return buffer.getvalue()