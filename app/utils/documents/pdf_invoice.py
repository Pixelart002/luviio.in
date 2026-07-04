"""
PDF Invoice Generator — Exact Amazon.in Layout (100% Dynamic SSOT)
==================================================================
Path: app/utils/documents/pdf_invoice.py

Generates a professional, Amazon-style 10-column Tax Invoice.
Strictly uses dynamic DB data with nested relation scanning and Indian GST logic.
"""
import io
import datetime
from decimal import Decimal
from typing import Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# ── Safe Currency Formatter ───────────────────────────────────────────────────
def format_currency(amount: Any, currency: str = "Rs.") -> str:
    if amount is None:
        return f"{currency} 0.00"
    try:
        val = float(amount)
        return f"{currency} {val:,.2f}"
    except (ValueError, TypeError):
        return f"{currency} 0.00"

# ── Safe Number Extractor ─────────────────────────────────────────────────────
def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default

# ── Multi-Layer Product Name Extractor ────────────────────────────────────────
def get_product_name(item: Dict[str, Any]) -> str:
    """Scans all possible flat and nested Supabase relation structures."""
    if item.get("product_name"):
        return str(item["product_name"])
    if item.get("name"):
        return str(item["name"])
    if isinstance(item.get("products"), dict) and item["products"].get("name"):
        return str(item["products"]["name"])
    if isinstance(item.get("product"), dict) and item["product"].get("name"):
        return str(item["product"]["name"])
    return "Sanitation / Bath Fitting Product"

# ── Dynamic Indian GST Type Resolver ──────────────────────────────────────────
def resolve_tax_type(shipping_state: str | None, seller_state: str = "DELHI") -> str:
    """Determines whether IGST or CGST+SGST applies based on Indian state rules."""
    if not shipping_state:
        return "IGST"
    
    buyer_st = str(shipping_state).strip().upper()
    seller_st = seller_state.upper()
    
    # Check if intra-state (Delhi / DL / New Delhi)
    if buyer_st in [seller_st, "DL", "NEW DELHI", "NCT OF DELHI"]:
        return "CGST+SGST"
    return "IGST"

# ── INR Number to Words Converter ─────────────────────────────────────────────
def num_to_words_inr(num: float) -> str:
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _convert(n: int) -> str:
        if n == 0: return ""
        elif n < 20: return ones[n] + " "
        elif n < 100: return tens[n // 10] + " " + _convert(n % 10)
        elif n < 1000: return ones[n // 100] + " Hundred " + _convert(n % 100)
        elif n < 100000: return _convert(n // 1000) + "Thousand " + _convert(n % 1000)
        elif n < 10000000: return _convert(n // 100000) + "Lakh " + _convert(n % 100000)
        else: return _convert(n // 10000000) + "Crore " + _convert(n % 10000000)

    try:
        total_int = int(num)
        paise_int = int(round((num - total_int) * 100))
        if total_int == 0 and paise_int == 0:
            return "Zero Rupees Only"
        
        res = _convert(total_int).strip() + " Rupees" if total_int > 0 else ""
        if paise_int > 0:
            res += (" And " if res else "") + _convert(paise_int).strip() + " Paise"
        return res + " Only"
    except Exception:
        return "Amount as per invoice"

# ── Main PDF Builder ──────────────────────────────────────────────────────────
def build_invoice_pdf(order: dict[str, Any], customer: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25
    )
    styles = getSampleStyleSheet()

    # Typography Styles
    title_right = ParagraphStyle('TitleR', parent=styles['Normal'], alignment=TA_RIGHT, fontName='Helvetica-Bold', fontSize=13, leading=16)
    brand_logo = ParagraphStyle('Brand', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=22, leading=26)
    norm = ParagraphStyle('Norm', parent=styles['Normal'], fontSize=8, leading=11)
    norm_bold = ParagraphStyle('NormB', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=11)
    norm_right = ParagraphStyle('NormR', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=8, leading=11)

    elements = []

    # 1. TOP BRAND & TITLE HEADER
    doc_type = "Refund Note / Credit Note" if order.get("status") == "refunded" else "Tax Invoice/Bill of Supply/Cash Memo"
    header_table = Table([
        [Paragraph("<b>LUVIIO.in</b>", brand_logo), Paragraph(f"<b>{doc_type}</b><br/><font size=8>(Original for Recipient)</font>", title_right)]
    ], colWidths=[245, 300])
    header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 12)]))
    elements.append(header_table)

    # 2. SELLER & BUYER DETAILS
    c_name = customer.get("full_name") or order.get("customer_name") or "Valued Customer"
    shipping_state = order.get("shipping_state") or ""
    addr_lines = [
        order.get("shipping_line1"), order.get("shipping_line2"),
        order.get("shipping_city"), shipping_state,
        order.get("shipping_postal_code"), order.get("shipping_country", "India")
    ]
    formatted_addr = "<br/>".join([str(x) for x in addr_lines if x])

    seller_block = """<b>Sold By:</b><br/>
LUVIIO E-Commerce Private Limited<br/>
National Highway 8, Sector 24<br/>
New Delhi, 110037, IN<br/><br/>
<b>PAN No:</b> AACCL1234F<br/>
<b>GST Registration No:</b> 07AACCL1234F1Z9"""

    buyer_block = f"""<b>Billing & Shipping Address:</b><br/>
<b>{c_name}</b><br/>{formatted_addr}"""

    order_num = str(order.get("id", ""))[:12].upper()
    order_dt = str(order.get("created_at", ""))[:10]
    inv_date = datetime.datetime.now().strftime("%d.%m.%Y")

    meta_left = f"<b>Order Number:</b> {order_num}<br/><b>Order Date:</b> {order_dt}"
    meta_right = f"<b>Invoice Number:</b> DEL-{order_num[:6]}<br/><b>Invoice Date:</b> {inv_date}"

    grid = Table([
        [Paragraph(seller_block, norm), Paragraph(buyer_block, norm_right)],
        [Spacer(1, 8), Spacer(1, 8)],
        [Paragraph(meta_left, norm), Paragraph(meta_right, norm_right)]
    ], colWidths=[270, 275])
    grid.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
    elements.append(grid)
    elements.append(Spacer(1, 12))

    # 3. AMAZON 10-COLUMN ITEMS TABLE (100% Dynamic)
    col_widths = [20, 160, 52, 24, 54, 45, 38, 38, 48, 66]
    
    table_data = [[
        Paragraph('<b>Sl. No</b>', norm_bold), Paragraph('<b>Description</b>', norm_bold),
        Paragraph('<b>Unit Price</b>', norm_bold), Paragraph('<b>Qty</b>', norm_bold),
        Paragraph('<b>Net Amount</b>', norm_bold), Paragraph('<b>Discount</b>', norm_bold),
        Paragraph('<b>Tax Rate</b>', norm_bold), Paragraph('<b>Tax Type</b>', norm_bold),
        Paragraph('<b>Tax Amount</b>', norm_bold), Paragraph('<b>Total Amount</b>', norm_bold)
    ]]

    items = order.get("order_items") or order.get("items") or []
    
    # Derive dynamic tax rules
    subtotal = safe_float(order.get("subtotal"), 0.0)
    total_tax_db = safe_float(order.get("tax_amount"), 0.0)
    
    # Calculate effective tax rate if not explicitly passed
    tax_rate_pct = safe_float(order.get("tax_rate_pct"), 0.0)
    if tax_rate_pct == 0.0 and subtotal > 0:
        tax_rate_pct = round((total_tax_db / subtotal) * 100)
    if tax_rate_pct == 0.0:
        tax_rate_pct = 18.0 # Standard bath hardware fallback rate

    tax_type = resolve_tax_type(shipping_state, seller_state="DELHI")

    tot_tax_sum = 0.0
    tot_net_sum = 0.0
    tot_disc_sum = 0.0

    for idx, item in enumerate(items, 1):
        name = get_product_name(item)
        qty = int(safe_float(item.get("quantity"), 1))
        
        # Real unit price & discount handling
        unit_p = safe_float(item.get("unit_price") or item.get("price") or item.get("price_snapshot"))
        compare_p = safe_float(item.get("compare_price"))
        
        item_disc = safe_float(item.get("discount_amount") or item.get("discount"))
        if item_disc == 0.0 and compare_p > unit_p:
            item_disc = (compare_p - unit_p) * qty
            
        net_amt = unit_p * qty
        tax_amt = round(net_amt * (tax_rate_pct / 100.0), 2)
        total_item_amt = net_amt + tax_amt

        tot_net_sum += net_amt
        tot_tax_sum += tax_amt
        tot_disc_sum += item_disc

        table_data.append([
            Paragraph(str(idx), norm),
            Paragraph(name, norm),
            Paragraph(format_currency(unit_p), norm),
            Paragraph(str(qty), norm),
            Paragraph(format_currency(net_amt), norm),
            Paragraph(format_currency(item_disc), norm),
            Paragraph(f"{int(tax_rate_pct)}%", norm),
            Paragraph(tax_type, norm),
            Paragraph(format_currency(tax_amt), norm),
            Paragraph(format_currency(total_item_amt), norm)
        ])

    # 3.1 Dynamic Shipping Row
    shipping = safe_float(order.get("shipping_cost"))
    if shipping > 0:
        ship_tax = round(shipping * (tax_rate_pct / 100.0), 2)
        tot_tax_sum += ship_tax
        table_data.append([
            Paragraph("", norm),
            Paragraph("<b>Shipping Charges</b>", norm),
            Paragraph(format_currency(shipping), norm),
            Paragraph("1", norm),
            Paragraph(format_currency(shipping), norm),
            Paragraph(format_currency(0), norm),
            Paragraph(f"{int(tax_rate_pct)}%", norm),
            Paragraph(tax_type, norm),
            Paragraph(format_currency(ship_tax), norm),
            Paragraph(format_currency(shipping + ship_tax), norm)
        ])

    # 3.2 Dynamic Total Row
    grand_total = safe_float(order.get("total_amount"), tot_net_sum + tot_tax_sum)
    table_data.append([
        Paragraph("<b>Total:</b>", norm_bold), "", "", "", "", "", "", "",
        Paragraph(f"<b>{format_currency(tot_tax_sum)}</b>", norm_bold),
        Paragraph(f"<b>{format_currency(grand_total)}</b>", norm_bold)
    ])

    item_table = Table(table_data, colWidths=col_widths)
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#e0e0e0")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('SPAN', (0,-1), (7,-1)),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(item_table)

    # 4. AMOUNT IN WORDS & SIGNATORY BOX
    words = num_to_words_inr(grand_total)
    
    footer_table = Table([
        [Paragraph(f"<b>Amount in Words:</b><br/>{words}", norm_bold)],
        [Spacer(1, 15)],
        [Paragraph("<b>For LUVIIO E-Commerce Private Limited:</b><br/><br/><br/><b>Authorized Signatory</b>", norm_right)]
    ], colWidths=[545])
    footer_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f8f8f8")),
    ]))
    elements.append(footer_table)

    doc.build(elements)
    return buffer.getvalue()
