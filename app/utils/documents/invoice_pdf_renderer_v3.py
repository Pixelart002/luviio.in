"""Clean immutable-snapshot invoice renderer with explicit GST columns."""
from __future__ import annotations

import datetime
import io
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

W = 555.0
MARGIN = 20.0
BORDER = colors.HexColor("#bdbdbd")
HEADER = colors.HexColor("#f1f1f1")
ALT = colors.HexColor("#fafafa")
TOTAL = colors.HexColor("#e8e8e8")
GOLD = colors.HexColor("#c9a96e")
DIM = colors.HexColor("#555555")
LIGHT = colors.HexColor("#777777")


def _s(v: Any, default: str = "") -> str:
    if v is None:
        return default
    value = str(v).strip()
    return value if value and value.lower() not in {"none", "null"} else default


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _money(v: Any) -> str:
    return f"Rs. {_f(v):,.2f}"


def _date(v: Any) -> str:
    raw = _s(v)
    if not raw:
        return "—"
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d-%m-%Y")
    except ValueError:
        return raw[:10]


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    def st(name: str, **kw: Any) -> ParagraphStyle:
        return ParagraphStyle(name, parent=base, **kw)
    return {
        "logo": st("logo", fontName="Helvetica-Bold", fontSize=20, leading=23),
        "title": st("title", fontName="Helvetica-Bold", fontSize=12, leading=15, alignment=TA_RIGHT),
        "site": st("site", fontSize=7, leading=9, textColor=DIM),
        "right": st("right", fontSize=7, leading=9, alignment=TA_RIGHT, textColor=DIM),
        "label": st("label", fontName="Helvetica-Bold", fontSize=8, leading=10),
        "body": st("body", fontSize=7.1, leading=9),
        "body_b": st("body_b", fontName="Helvetica-Bold", fontSize=7.1, leading=9),
        "small": st("small", fontSize=6.2, leading=8, textColor=DIM),
        "head": st("head", fontName="Helvetica-Bold", fontSize=6.2, leading=7.4, alignment=TA_CENTER),
        "head_l": st("head_l", fontName="Helvetica-Bold", fontSize=6.2, leading=7.4, alignment=TA_LEFT),
        "head_r": st("head_r", fontName="Helvetica-Bold", fontSize=6.2, leading=7.4, alignment=TA_RIGHT),
        "cell": st("cell", fontSize=6.3, leading=8),
        "cell_c": st("cell_c", fontSize=6.3, leading=8, alignment=TA_CENTER),
        "cell_r": st("cell_r", fontSize=6.3, leading=8, alignment=TA_RIGHT),
        "cell_b": st("cell_b", fontName="Helvetica-Bold", fontSize=6.3, leading=8),
        "sum_l": st("sum_l", fontSize=7.2, leading=9, alignment=TA_RIGHT),
        "sum_v": st("sum_v", fontName="Helvetica-Bold", fontSize=7.2, leading=9, alignment=TA_RIGHT),
        "words": st("words", fontSize=7.2, leading=9.2),
        "sign": st("sign", fontSize=7.1, leading=9, alignment=TA_RIGHT),
        "section": st("section", fontName="Helvetica-Bold", fontSize=8, leading=10),
        "foot": st("foot", fontSize=6, leading=7.4, alignment=TA_CENTER, textColor=LIGHT),
    }


def _amount_words(amount: float) -> str:
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    def w(n: int) -> str:
        if n == 0: return ""
        if n < 20: return ones[n] + " "
        if n < 100: return tens[n // 10] + ((" " + ones[n % 10]) if n % 10 else "") + " "
        if n < 1000: return ones[n // 100] + " Hundred " + w(n % 100)
        if n < 100000: return w(n // 1000) + "Thousand " + w(n % 1000)
        if n < 10000000: return w(n // 100000) + "Lakh " + w(n % 100000)
        return w(n // 10000000) + "Crore " + w(n % 10000000)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    if paise == 100: rupees, paise = rupees + 1, 0
    parts = []
    if rupees: parts.append(w(rupees).strip() + " Rupees")
    if paise: parts.append(w(paise).strip() + " Paise")
    return " and ".join(parts) + " Only" if parts else "Zero Rupees Only"


def _state_code(state: str) -> str:
    return {"delhi": "DL", "new delhi": "DL", "haryana": "HR", "uttar pradesh": "UP", "maharashtra": "MH", "karnataka": "KA", "punjab": "PB", "rajasthan": "RJ"}.get(state.strip().lower(), state.strip().upper()[:2]) if state else ""


def _payment_status(order: dict[str, Any]) -> str:
    raw = _s(order.get("payment_status")) or _s(order.get("payment_state")) or _s(order.get("status"))
    return {"succeeded": "PAID", "paid": "PAID", "pending": "PENDING", "processing": "PROCESSING", "failed": "FAILED", "refunded": "REFUNDED", "cancelled": "CANCELLED", "canceled": "CANCELLED", "requires_action": "ACTION REQUIRED", "requires_payment_method": "PAYMENT REQUIRED"}.get(raw.lower(), raw.upper() if raw else "PENDING")


def _tax_type(order: dict[str, Any]) -> str:
    return _s(order.get("tax_type"), "IGST").upper().replace("CGST_SGST", "CGST+SGST").replace("CGST/SGST", "CGST+SGST")


def _qr(data: str, size: float = 68) -> Drawing:
    widget = QrCodeWidget(data or "LUVIIO")
    x1, y1, x2, y2 = widget.getBounds()
    return Drawing(size, size, transform=[size / (x2-x1), 0, 0, size / (y2-y1), 0, 0], contents=[widget])


def _asset(url: str, width: float, height: float) -> Image | None:
    value = _s(url)
    if not value:
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or "/storage/v1/object/public/business-assets/" not in parsed.path:
            return None
        data = urlopen(Request(value, headers={"User-Agent": "Luviio-Invoice/1.0"}), timeout=4).read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            return None
        return Image(io.BytesIO(data), width=width, height=height)
    except Exception:
        return None


def _addr(snapshot: dict[str, Any], fallback: str, styles: dict[str, ParagraphStyle]) -> list[list[Any]]:
    p = snapshot or {}
    name = _s(p.get("name"), fallback)
    rows = [[Paragraph(_s(p.get("company_name"), name), styles["body_b"])]]
    if _s(p.get("company_name")) and name:
        rows.append([Paragraph(f"Attn: {name}", styles["body"])])
    if _s(p.get("gstin")): rows.append([Paragraph(f"<b>Buyer GSTIN:</b> {_s(p.get('gstin'))}", styles["body"])])
    for key in ("line1", "line2", "landmark", "city", "district", "state", "postal_code", "country"):
        if _s(p.get(key)): rows.append([Paragraph(_s(p.get(key)), styles["body"])])
    if _s(p.get("phone")): rows.append([Paragraph(f"Ph: {_s(p.get('phone'))}", styles["small"])])
    if _s(p.get("email")): rows.append([Paragraph(_s(p.get("email")), styles["small"])])
    return rows


def build_snapshot_invoice_pdf(invoice_order: dict[str, Any], customer: dict[str, Any], seller_snapshot: dict[str, Any], billing_snapshot: dict[str, Any], shipping_snapshot: dict[str, Any]) -> bytes:
    s = _styles()
    order, seller, billing, shipping = invoice_order or {}, seller_snapshot or {}, billing_snapshot or {}, shipping_snapshot or {}
    tax_type = _tax_type(order)
    intra = tax_type == "CGST+SGST"
    invoice_no = _s(order.get("invoice_number"), "—")
    order_no = _s(order.get("order_number"), _s(order.get("id"), "—"))
    payment = _payment_status(order)
    seller_name = _s(seller.get("legal_name"), _s(seller.get("brand_name"), "LUVIIO"))
    website = _s(seller.get("website"), "https://luviio.in")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN, title=f"Luviio Invoice #{invoice_no}")
    story: list[Any] = []

    logo = _asset(seller.get("logo_url"), 98, 40)
    header = Table([[logo or Paragraph("LUVIIO", s["logo"]), Paragraph("TAX INVOICE", s["title"])], [Paragraph(website, s["site"]), Paragraph("Original for Recipient", s["right"])]], colWidths=[W*.58, W*.42])
    header.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "BOTTOM"), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 2)]))
    story += [header, HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=6)]

    def panel(rows: list[list[Any]], width: float) -> Table:
        t = Table(rows, colWidths=[width-12])
        t.setStyle(TableStyle([("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0), ("TOPPADDING", (0,0), (-1,-1), 1), ("BOTTOMPADDING", (0,0), (-1,-1), 1)]))
        return t

    sold = [[Paragraph("Sold By:", s["label"])], [Paragraph(seller_name, s["body_b"])]]
    for key in ("address_1", "address_2", "city", "district", "state", "pincode", "country"):
        if _s(seller.get(key)): sold.append([Paragraph(_s(seller.get(key)), s["body"])])
    if _s(seller.get("email")): sold.append([Paragraph(_s(seller.get("email")), s["small"])])
    if _s(seller.get("pan")): sold.append([Paragraph(f"<b>PAN:</b> {_s(seller.get('pan'))}", s["body"])])
    if _s(seller.get("gstin")): sold.append([Paragraph(f"<b>GSTIN:</b> {_s(seller.get('gstin'))}", s["body"])])
    top = Table([[panel(sold,185), panel([[Paragraph("Billed To:", s["label"])]] + _addr(billing, _s(customer.get("full_name"), "Valued Customer"), s),185), panel([[Paragraph("Shipped To:", s["label"])]] + _addr(shipping, _s(customer.get("full_name"), "Valued Customer"), s),185)]], colWidths=[185,185,185])
    top.setStyle(TableStyle([("BOX", (0,0), (-1,-1), .5, BORDER), ("LINEBEFORE", (1,0), (1,0), .5, BORDER), ("LINEBEFORE", (2,0), (2,0), .5, BORDER), ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6)]))
    story += [top, Spacer(1,5)]

    place = _s(shipping.get("state"), "—")
    code = _state_code(place)
    meta_left = [[Paragraph("Order Details:", s["label"])], [Paragraph(f"<b>Order No:</b> {order_no}", s["body"])], [Paragraph(f"<b>Order Date:</b> {_date(order.get('created_at'))}", s["body"])]]
    meta_mid = [[Paragraph("Invoice Details:", s["label"])], [Paragraph(f"<b>Invoice No:</b> {invoice_no}", s["body"])], [Paragraph(f"<b>Invoice Date:</b> {_date(order.get('issued_at'))}", s["body"])], [Paragraph(f"<b>Payment Status:</b> {payment}", s["body_b"])], [Paragraph(f"<b>Tracking:</b> {_s(order.get('tracking_number'), '—')}", s["body"])], [Paragraph(f"<b>Place of Supply:</b> {place} ({code})", s["body"])], [Paragraph(f"<b>Reverse Charge:</b> {_s(order.get('reverse_charge'), 'No')}", s["body"])]]
    qr = Table([[Paragraph("SCAN TO VERIFY", s["head"])], [_qr(_s(order.get("qr_payload"), f"INV:{invoice_no}|ORD:{order_no}|TOTAL:{_f(order.get('total_amount')):.2f}") )]], colWidths=[105])
    meta = Table([[panel(meta_left,225), panel(meta_mid,225), qr]], colWidths=[225,225,105])
    meta.setStyle(TableStyle([("BOX", (0,0), (-1,-1), .5, BORDER), ("LINEBEFORE", (1,0), (1,0), .5, BORDER), ("LINEBEFORE", (2,0), (2,0), .5, BORDER), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6)]))
    story += [meta, Spacer(1,7)]

    if intra:
        widths = [18,137,36,48,22,45,54,42,44,44,65]
        heads = ["Sl.", "Description", "HSN", "Unit Price (Rs.)", "Qty", "Discount (Rs.)", "Net Amount (Rs.)", "GST Rate", "CGST (Rs.)", "SGST (Rs.)", "Total (Rs.)"]
    else:
        widths = [18,145,38,50,22,48,56,55,73]
        heads = ["Sl.", "Description", "HSN", "Unit Price (Rs.)", "Qty", "Discount (Rs.)", "Net Amount (Rs.)", "GST Rate / IGST", "Total (Rs.)"]
    styles_head = [s["head"], s["head_l"], s["head"], s["head_r"], s["head"], s["head_r"], s["head_r"], s["head"], s["head_r"], s["head_r"], s["head_r"]]
    rows = [[Paragraph(h, styles_head[i]) for i, h in enumerate(heads)]]
    breakdown: dict[tuple[str,float], dict[str,float]] = {}
    run_net = 0.0
    run_tax = 0.0

    for idx, item in enumerate(order.get("order_items") or [], 1):
        qty = max(1, int(_f(item.get("quantity"), 1)))
        unit = _f(item.get("unit_price"))
        compare = max(_f(item.get("compare_price")), _f(item.get("compare_price_snapshot")), _f(item.get("mrp")))
        display_unit = max(unit, compare)
        discount = max(0.0, _f(item.get("discount_amount")))
        if discount <= 0 and display_unit > unit: discount = (display_unit-unit) * qty
        net = _f(item.get("taxable_value"), _f(item.get("subtotal"), unit*qty))
        rate = _f(item.get("gst_percentage"))
        tax = _f(item.get("tax_amount"))
        if tax <= 0 and rate > 0: tax = round(net*rate/100, 2)
        if intra:
            cgst = round(tax/2,2); sgst = round(tax-cgst,2); igst = 0.0
        else:
            cgst = sgst = 0.0; igst = round(tax,2)
        total = _f(item.get("line_total"), net+tax)
        run_net += net; run_tax += tax
        hsn = _s(item.get("hsn_code"), "—")
        bucket = breakdown.setdefault((hsn,rate), {"net":0.0,"cgst":0.0,"sgst":0.0,"igst":0.0,"tax":0.0})
        bucket["net"] += net; bucket["cgst"] += cgst; bucket["sgst"] += sgst; bucket["igst"] += igst; bucket["tax"] += tax
        rate_text = f"{rate:g}%"
        if intra: rate_text += f"<br/>({rate/2:g}% + {rate/2:g}%)"
        common = [Paragraph(str(idx),s["cell_c"]), Paragraph(_s(item.get("product_name"),"Product"),s["cell"]), Paragraph(hsn,s["cell_c"]), Paragraph(_money(display_unit),s["cell_r"]), Paragraph(str(qty),s["cell_c"]), Paragraph(_money(discount),s["cell_r"]), Paragraph(_money(net),s["cell_r"]), Paragraph(rate_text if intra else f"{rate:g}%<br/>IGST",s["cell_c"])]
        rows.append(common + ([Paragraph(_money(cgst),s["cell_r"]),Paragraph(_money(sgst),s["cell_r"]),Paragraph(_money(total),s["cell_r"])] if intra else [Paragraph(_money(total),s["cell_r"]) ]))

    shipping_cost = _f(order.get("shipping_cost"))
    if shipping_cost > 0:
        common = [Paragraph("",s["cell"]),Paragraph("Shipping Charges",s["cell_b"]),Paragraph(_s(order.get("shipping_hsn"),"—"),s["cell_c"]),Paragraph(_money(shipping_cost),s["cell_r"]),Paragraph("1",s["cell_c"]),Paragraph(_money(0),s["cell_r"]),Paragraph(_money(shipping_cost),s["cell_r"]),Paragraph("—",s["cell_c"])]
        rows.append(common + ([Paragraph(_money(0),s["cell_r"]),Paragraph(_money(0),s["cell_r"]),Paragraph(_money(shipping_cost),s["cell_r"])] if intra else [Paragraph(_money(shipping_cost),s["cell_r"])]))

    subtotal = _f(order.get("subtotal"), run_net)
    tax_total = _f(order.get("tax_amount"), run_tax)
    grand = _f(order.get("total_amount"), subtotal+shipping_cost+tax_total)
    rates = sorted({rate for _, rate in breakdown})
    total_rate = " / ".join(f"{r:g}%" for r in rates) if rates else "—"
    total_row = [Paragraph("Total",s["cell_b"]),"","","","","",Paragraph(_money(run_net),s["head_r"]),Paragraph(total_rate,s["head"])]
    if intra:
        total_row += [Paragraph(_money(sum(v["cgst"] for v in breakdown.values())),s["head_r"]),Paragraph(_money(sum(v["sgst"] for v in breakdown.values())),s["head_r"]),Paragraph(_money(grand),s["head_r"])]
    else:
        total_row += [Paragraph(_money(grand),s["head_r"])]
    rows.append(total_row)
    table = Table(rows,colWidths=widths,repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),HEADER),("BACKGROUND",(0,-1),(-1,-1),TOTAL),("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.white,ALT]),("BOX",(0,0),(-1,-1),.5,BORDER),("INNERGRID",(0,0),(-1,-1),.25,colors.HexColor("#dddddd")),("SPAN",(0,-1),(5,-1)),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story += [table,Spacer(1,7)]

    gst_title = "GST BREAKDOWN — CGST + SGST" if intra else "GST BREAKDOWN — IGST"
    gst_rows = [[Paragraph(gst_title,s["section"])]]
    if intra:
        gst_rows.append([Paragraph(x,s["head"]) for x in ["HSN","Taxable Value (Rs.)","GST Rate","CGST (Rs.)","SGST (Rs.)","Total GST (Rs.)"]])
        for (hsn,rate),v in sorted(breakdown.items()):
            gst_rows.append([Paragraph(hsn,s["cell_c"]),Paragraph(_money(v["net"]),s["cell_r"]),Paragraph(f"{rate:g}%<br/>({rate/2:g}% + {rate/2:g}%)",s["cell_c"]),Paragraph(_money(v["cgst"]),s["cell_r"]),Paragraph(_money(v["sgst"]),s["cell_r"]),Paragraph(_money(v["tax"]),s["cell_r"])])
        gst_rows.append([Paragraph("Total",s["cell_b"]),Paragraph(_money(sum(v["net"] for v in breakdown.values())),s["cell_r"]),"",Paragraph(_money(sum(v["cgst"] for v in breakdown.values())),s["cell_r"]),Paragraph(_money(sum(v["sgst"] for v in breakdown.values())),s["cell_r"]),Paragraph(_money(sum(v["tax"] for v in breakdown.values())),s["cell_r"])])
        gst_widths=[58,125,80,95,95,102]
    else:
        gst_rows.append([Paragraph(x,s["head"]) for x in ["HSN","Taxable Value (Rs.)","GST Rate","IGST (Rs.)","Total GST (Rs.)"]])
        for (hsn,rate),v in sorted(breakdown.items()): gst_rows.append([Paragraph(hsn,s["cell_c"]),Paragraph(_money(v["net"]),s["cell_r"]),Paragraph(f"{rate:g}%",s["cell_c"]),Paragraph(_money(v["igst"]),s["cell_r"]),Paragraph(_money(v["tax"]),s["cell_r"])])
        gst_rows.append([Paragraph("Total",s["cell_b"]),Paragraph(_money(sum(v["net"] for v in breakdown.values())),s["cell_r"]),"",Paragraph(_money(sum(v["igst"] for v in breakdown.values())),s["cell_r"]),Paragraph(_money(sum(v["tax"] for v in breakdown.values())),s["cell_r"])])
        gst_widths=[65,150,90,120,130]
    gst = Table(gst_rows,colWidths=gst_widths,repeatRows=2)
    gst.setStyle(TableStyle([("SPAN",(0,0),(-1,0)),("BACKGROUND",(0,0),(-1,0),TOTAL),("BACKGROUND",(0,1),(-1,1),HEADER),("BACKGROUND",(0,-1),(-1,-1),TOTAL),("BOX",(0,0),(-1,-1),.5,BORDER),("INNERGRID",(0,1),(-1,-1),.25,colors.HexColor("#dddddd")),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3)]))
    story += [gst,Spacer(1,6)]

    summary = Table([[Paragraph("Price Summary:",s["label"]),""],[Paragraph("Subtotal",s["sum_l"]),Paragraph(_money(subtotal),s["sum_v"])],[Paragraph("Shipping",s["sum_l"]),Paragraph(_money(shipping_cost) if shipping_cost else "FREE",s["sum_v"])],[Paragraph("GST",s["sum_l"]),Paragraph(_money(tax_total),s["sum_v"])],[Paragraph("Grand Total",s["sum_l"]),Paragraph(_money(grand),s["sum_v"]) ]],colWidths=[150,84])
    summary.setStyle(TableStyle([("LINEABOVE",(0,-1),(-1,-1),.8,BORDER),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
    sign = [[Paragraph(f"<b>For {seller_name}:</b>",s["sign"])],[Spacer(1,4)],[Paragraph(_s(seller.get("authorised_signatory_name")),s["sign"])],[Paragraph(_s(seller.get("authorised_signatory_designation"),"Authorised Signatory"),s["sign"])]]
    bottom = Table([[Table([[Paragraph("Amount in Words:",s["label"])],[Paragraph(_amount_words(grand),s["words"])]],colWidths=[288]),Table([[summary],[Spacer(1,5)],*sign],colWidths=[234])]],colWidths=[304,250])
    bottom.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.5,BORDER),("LINEBEFORE",(1,0),(1,0),.5,BORDER),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7)]))
    story += [bottom,Spacer(1,5),HRFlowable(width="100%",thickness=.4,color=BORDER,spaceAfter=3)]
    footer=f"This is a computer-generated invoice and does not require a physical signature. For queries, contact {_s(seller.get('email'),'support@luviio.in')} | {website}"
    if _s(seller.get("gstin")): footer += f" | GSTIN: {_s(seller.get('gstin'))}"
    story.append(Paragraph(footer,s["foot"]))
    doc.build(story)
    return buf.getvalue()
