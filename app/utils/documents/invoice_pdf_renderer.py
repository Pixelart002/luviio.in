"""Immutable-snapshot GST invoice PDF renderer for Luviio."""
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
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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


def _date(v: Any, fallback_now: bool = False) -> str:
    raw = _s(v)
    if not raw:
        return datetime.datetime.now().strftime("%d-%m-%Y") if fallback_now else "—"
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d-%m-%Y")
    except ValueError:
        return raw[:10]


def _qr(data: str, size: float = 72.0) -> Drawing:
    widget = QrCodeWidget(data or "LUVIIO")
    x1, y1, x2, y2 = widget.getBounds()
    width, height = x2 - x1, y2 - y1
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(widget)
    return drawing


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    def st(name: str, **kw: Any) -> ParagraphStyle:
        return ParagraphStyle(name, parent=base, **kw)
    return {
        "logo": st("logo", fontName="Helvetica-Bold", fontSize=20, leading=23),
        "title": st("title", fontName="Helvetica-Bold", fontSize=12, leading=15, alignment=TA_RIGHT),
        "site": st("site", fontSize=7, leading=9, textColor=DIM),
        "small_right": st("small_right", fontSize=7, leading=9, alignment=TA_RIGHT, textColor=DIM),
        "label": st("label", fontName="Helvetica-Bold", fontSize=8, leading=10),
        "body": st("body", fontSize=7.3, leading=9.5),
        "body_b": st("body_b", fontName="Helvetica-Bold", fontSize=7.3, leading=9.5),
        "small": st("small", fontSize=6.5, leading=8.5, textColor=DIM),
        "head": st("head", fontName="Helvetica-Bold", fontSize=6.7, leading=8, alignment=TA_CENTER),
        "head_l": st("head_l", fontName="Helvetica-Bold", fontSize=6.7, leading=8, alignment=TA_LEFT),
        "head_r": st("head_r", fontName="Helvetica-Bold", fontSize=6.7, leading=8, alignment=TA_RIGHT),
        "cell": st("cell", fontSize=6.7, leading=8.8),
        "cell_c": st("cell_c", fontSize=6.7, leading=8.8, alignment=TA_CENTER),
        "cell_r": st("cell_r", fontSize=6.7, leading=8.8, alignment=TA_RIGHT),
        "cell_b": st("cell_b", fontName="Helvetica-Bold", fontSize=6.7, leading=8.8),
        "sum_l": st("sum_l", fontSize=7.5, leading=10, alignment=TA_RIGHT),
        "sum_v": st("sum_v", fontName="Helvetica-Bold", fontSize=7.5, leading=10, alignment=TA_RIGHT),
        "words": st("words", fontSize=7.4, leading=10),
        "sign": st("sign", fontSize=7.4, leading=10, alignment=TA_RIGHT),
        "foot": st("foot", fontSize=6.2, leading=8, alignment=TA_CENTER, textColor=LIGHT),
    }


def _amount_words(amount: float) -> str:
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    def n2w(n: int) -> str:
        if n == 0: return ""
        if n < 20: return ones[n] + " "
        if n < 100: return tens[n // 10] + ((" " + ones[n % 10]) if n % 10 else "") + " "
        if n < 1000: return ones[n // 100] + " Hundred " + n2w(n % 100)
        if n < 100000: return n2w(n // 1000) + "Thousand " + n2w(n % 1000)
        if n < 10000000: return n2w(n // 100000) + "Lakh " + n2w(n % 100000)
        return n2w(n // 10000000) + "Crore " + n2w(n % 10000000)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    if paise == 100: rupees, paise = rupees + 1, 0
    parts = []
    if rupees: parts.append(n2w(rupees).strip() + " Rupees")
    if paise: parts.append(n2w(paise).strip() + " Paise")
    return (" and ".join(parts) + " Only") if parts else "Zero Rupees Only"


def _remote_asset(url: str, *, max_bytes: int = 2 * 1024 * 1024) -> bytes | None:
    value = _s(url)
    if not value: return None
    try:
        parsed = urlparse(value)
        if parsed.scheme != "https" or "/storage/v1/object/public/business-assets/" not in parsed.path:
            return None
        response = urlopen(Request(value, headers={"User-Agent": "Luviio-Invoice/1.0"}), timeout=4)
        data = response.read(max_bytes + 1)
        return data if len(data) <= max_bytes else None
    except Exception:
        return None


def _asset_image(url: str, width: float, height: float) -> Image | None:
    data = _remote_asset(url)
    if not data: return None
    image = Image(io.BytesIO(data), width=width, height=height)
    image.hAlign = "CENTER"
    image._restrictSize(width, height)
    return image


def _address_rows(snapshot: dict[str, Any], fallback_name: str = "") -> list[list[Any]]:
    p = snapshot or {}
    name = _s(p.get("name"), fallback_name)
    company = _s(p.get("company_name"))
    rows: list[list[Any]] = []
    if company:
        rows += [[Paragraph(company, ST["body_b"])], [Paragraph(f"Attn: {name}", ST["body"])]]
    elif name:
        rows.append([Paragraph(name, ST["body_b"])])
    if _s(p.get("gstin")):
        rows.append([Paragraph(f"<b>Buyer GSTIN:</b> {_s(p.get('gstin'))}", ST["body"])])
    for key in ("line1", "line2", "landmark", "city", "district", "state", "postal_code", "country"):
        value = _s(p.get(key))
        if value: rows.append([Paragraph(value, ST["body"])])
    if _s(p.get("phone")): rows += [[Spacer(1,2)], [Paragraph(f"Ph: {_s(p.get('phone'))}", ST["small"])]]
    if _s(p.get("email")): rows.append([Paragraph(_s(p.get("email")), ST["small"])])
    return rows


def _compare_price(item: dict[str, Any]) -> float:
    for key in ("compare_price", "compare_price_snapshot", "mrp"):
        value = _f(item.get(key))
        if value > 0: return value
    metadata = item.get("metadata") or {}
    value = _f(metadata.get("compare_price"))
    if value > 0: return value
    for rel in ("products", "product", "item"):
        obj = item.get(rel)
        if isinstance(obj, list): obj = obj[0] if obj and isinstance(obj[0], dict) else {}
        if isinstance(obj, dict):
            for key in ("compare_price", "mrp", "original_price"):
                value = _f(obj.get(key))
                if value > 0: return value
    return 0.0


def _line_discount(item: dict[str, Any], unit_price: float, qty: int) -> tuple[float, float]:
    compare = _compare_price(item)
    display_mrp = max(compare, unit_price)
    derived_discount = max(0.0, (display_mrp - unit_price) * qty)
    stored_discount = max(0.0, _f(item.get("discount_amount")))
    discount = stored_discount if stored_discount > 0 else derived_discount
    return display_mrp, discount


def _gst_display(item: dict[str, Any], order: dict[str, Any], tax_amount: float, rate: float) -> str:
    if rate <= 0 or tax_amount <= 0:
        return "—"
    tax_type = _s(order.get("tax_type"), "IGST")
    if tax_type == "CGST+SGST":
        half = round(tax_amount / 2, 2)
        other = round(tax_amount - half, 2)
        half_rate = rate / 2
        return f"<b>{rate:g}% GST</b><br/>CGST {half_rate:g}% + SGST {half_rate:g}%<br/><font color='#555555'>{_money(half)} + {_money(other)} = {_money(tax_amount)}</font>"
    return f"<b>{rate:g}% GST</b><br/>{tax_type} {rate:g}%<br/><font color='#555555'>{_money(tax_amount)}</font>"


def build_snapshot_invoice_pdf(invoice_order: dict[str, Any], customer: dict[str, Any], seller_snapshot: dict[str, Any], billing_snapshot: dict[str, Any], shipping_snapshot: dict[str, Any]) -> bytes:
    global ST
    ST = _styles()
    seller = seller_snapshot or {}
    billing = billing_snapshot or {}
    shipping = shipping_snapshot or {}
    order = invoice_order or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN, title=f"Luviio Invoice #{_s(order.get('invoice_number'))}")
    story: list[Any] = []

    invoice_no = _s(order.get("invoice_number")) or "—"
    order_no = _s(order.get("order_number")) or _s(order.get("id")) or "—"
    status = _s(order.get("status"), "paid").upper()
    website = _s(seller.get("website"), "https://luviio.in")
    seller_name = _s(seller.get("legal_name"), _s(seller.get("brand_name"), "LUVIIO"))

    logo = _asset_image(seller.get("logo_url"), 98, 42)
    brand_cell = logo or Paragraph("LUVIIO", ST["logo"])
    hdr = Table([[brand_cell, Paragraph("TAX INVOICE", ST["title"])], [Paragraph(website, ST["site"]), Paragraph("Original for Recipient", ST["small_right"])]], colWidths=[W*.58, W*.42])
    hdr.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"BOTTOM"),("BOTTOMPADDING",(0,0),(-1,-1),2),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    story += [hdr, HRFlowable(width="100%", thickness=2.2, color=GOLD, spaceAfter=8)]

    seller_rows = [[Paragraph("Sold By:", ST["label"])], [Paragraph(seller_name, ST["body_b"])]]
    for key in ("address_1", "address_2", "city", "district", "state", "pincode", "country"):
        value = _s(seller.get(key))
        if value: seller_rows.append([Paragraph(value, ST["body"])])
    if _s(seller.get("email")): seller_rows += [[Spacer(1,2)], [Paragraph(_s(seller.get("email")), ST["small"])]]
    if _s(seller.get("pan")): seller_rows.append([Paragraph(f"<b>PAN:</b> {_s(seller.get('pan'))}", ST["body"])])
    if _s(seller.get("gstin")): seller_rows.append([Paragraph(f"<b>GSTIN:</b> {_s(seller.get('gstin'))}", ST["body"])])
    billing_rows = [[Paragraph("Billed To:", ST["label"])]] + _address_rows(billing, _s(customer.get("full_name"), "Valued Customer"))
    shipping_rows = [[Paragraph("Shipped To:", ST["label"])]] + _address_rows(shipping, _s(customer.get("full_name"), "Valued Customer"))

    def panel(rows: list[list[Any]], width: float) -> Table:
        t = Table(rows, colWidths=[width-12])
        t.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1)]))
        return t

    top = Table([[panel(seller_rows,185),panel(billing_rows,185),panel(shipping_rows,185)]], colWidths=[185,185,185])
    top.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.5,BORDER),("LINEBEFORE",(1,0),(1,0),.5,BORDER),("LINEBEFORE",(2,0),(2,0),.5,BORDER),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [top, Spacer(1,6)]

    order_meta = [[Paragraph("Order Details:",ST["label"])],[Paragraph(f"<b>Order No:</b> {order_no}",ST["body"])],[Paragraph(f"<b>Order Date:</b> {_date(order.get('created_at'))}",ST["body"])]]
    invoice_meta = [[Paragraph("Invoice Details:",ST["label"])],[Paragraph(f"<b>Invoice No:</b> {invoice_no}",ST["body"])],[Paragraph(f"<b>Invoice Date:</b> {_date(order.get('issued_at'),True)}",ST["body"])],[Paragraph(f"<b>Payment:</b> {status}",ST["body"])],[Paragraph(f"<b>Tracking:</b> {_s(order.get('tracking_number'),'—')}",ST["body"])]]
    qr_payload = _s(order.get("qr_payload")) or f"INV:{invoice_no}|ORD:{order_no}|TOTAL:{_f(order.get('total_amount')):.2f}"
    qr_cell = Table([[Paragraph("SCAN TO VERIFY",ST["head"])],[_qr(qr_payload,72)]], colWidths=[105])
    qr_cell.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0)]))
    meta = Table([[panel(order_meta,225),panel(invoice_meta,225),qr_cell]], colWidths=[225,225,105])
    meta.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.5,BORDER),("LINEBEFORE",(1,0),(1,0),.5,BORDER),("LINEBEFORE",(2,0),(2,0),.5,BORDER),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story += [meta, Spacer(1,10)]

    widths = [18, 150, 38, 50, 22, 52, 60, 86, 66]
    rows = [[Paragraph("Sl.",ST["head"]),Paragraph("Description",ST["head_l"]),Paragraph("HSN",ST["head"]),Paragraph("Unit Price",ST["head_r"]),Paragraph("Qty",ST["head"]),Paragraph("Discount",ST["head_r"]),Paragraph("Net Amount",ST["head_r"]),Paragraph("GST",ST["head"]),Paragraph("Total",ST["head_r"])]]
    items = order.get("order_items") or []
    run_tax = 0.0
    run_net = 0.0
    for idx, item in enumerate(items,1):
        qty = max(1, int(_f(item.get("quantity"),1)))
        unit = _f(item.get("unit_price"))
        display_unit, discount = _line_discount(item, unit, qty)
        net = _f(item.get("taxable_value"))
        if net <= 0: net = _f(item.get("subtotal"), unit * qty)
        if net <= 0: net = unit * qty
        rate = _f(item.get("gst_percentage"))
        item_tax = max(0.0, _f(item.get("tax_amount")))
        if item_tax == 0 and rate > 0 and net > 0: item_tax = round(net * rate / 100,2)
        line_total = _f(item.get("line_total"))
        if line_total <= 0: line_total = net + item_tax
        tax_display = _gst_display(item, order, item_tax, rate)
        name = _s(item.get("product_name"), "Product")
        hsn = _s(item.get("hsn_code"))
        rows.append([Paragraph(str(idx),ST["cell_c"]),Paragraph(name,ST["cell"]),Paragraph(hsn,ST["cell_c"]),Paragraph(_money(display_unit),ST["cell_r"]),Paragraph(str(qty),ST["cell_c"]),Paragraph(_money(discount),ST["cell_r"]),Paragraph(_money(net),ST["cell_r"]),Paragraph(tax_display,ST["cell_c"]),Paragraph(_money(line_total),ST["cell_r"])])
        run_tax += item_tax
        run_net += net

    shipping_cost = _f(order.get("shipping_cost"))
    if shipping_cost > 0:
        rows.append([Paragraph("",ST["cell"]),Paragraph("Shipping Charges",ST["cell_b"]),Paragraph("9965",ST["cell_c"]),Paragraph(_money(shipping_cost),ST["cell_r"]),Paragraph("1",ST["cell_c"]),Paragraph(_money(0),ST["cell_r"]),Paragraph(_money(shipping_cost),ST["cell_r"]),Paragraph("—",ST["cell_c"]),Paragraph(_money(shipping_cost),ST["cell_r"])])
        run_net += shipping_cost

    grand = _f(order.get("total_amount"), run_net + run_tax)
    rows.append([Paragraph("Total",ST["cell_b"]),"","","","","","",Paragraph(_money(run_tax),ST["head_r"]),Paragraph(_money(grand),ST["head_r"])])
    items_table = Table(rows,colWidths=widths,repeatRows=1)
    items_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),HEADER),("LINEBELOW",(0,0),(-1,0),.8,BORDER),("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.white,ALT]),("BACKGROUND",(0,-1),(-1,-1),TOTAL),("SPAN",(0,-1),(6,-1)),("BOX",(0,0),(-1,-1),.5,BORDER),("INNERGRID",(0,0),(-1,-1),.25,colors.HexColor("#dddddd")),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story += [items_table,Spacer(1,10)]

    subtotal = _f(order.get("subtotal"), run_net-shipping_cost)
    tax_total = _f(order.get("tax_amount"), run_tax)
    summary = Table([[Paragraph("Price Summary:",ST["label"]),""],[Paragraph("Subtotal",ST["sum_l"]),Paragraph(_money(subtotal),ST["sum_v"])],[Paragraph("Shipping",ST["sum_l"]),Paragraph(_money(shipping_cost) if shipping_cost else "FREE",ST["sum_v"])],[Paragraph("GST",ST["sum_l"]),Paragraph(_money(tax_total),ST["sum_v"])],["",""] ,[Paragraph("Grand Total",ST["sum_l"]),Paragraph(_money(grand),ST["sum_v"]) ]],colWidths=[150,84])
    summary.setStyle(TableStyle([("LINEABOVE",(0,-1),(-1,-1),.8,BORDER),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))

    sign_name = _s(seller.get("authorised_signatory_name"))
    sign_designation = _s(seller.get("authorised_signatory_designation"))
    signature = _asset_image(seller.get("signature_url"),145,52)
    sign_rows = [[summary],[Spacer(1,8)],[Paragraph(f"<b>For {seller_name}:</b>",ST["sign"])],[Spacer(1,5)]]
    if signature: sign_rows += [[signature],[Spacer(1,3)]]
    else: sign_rows.append([Spacer(1,35)])
    if sign_name: sign_rows.append([Paragraph(f"<b>{sign_name}</b>",ST["sign"])])
    if sign_designation: sign_rows.append([Paragraph(sign_designation,ST["sign"])])
    sign_rows.append([Paragraph("Authorised Signatory",ST["sign"])])
    left = [[Paragraph("Amount in Words:",ST["label"])],[Spacer(1,3)],[Paragraph(_amount_words(grand),ST["words"])]]
    bottom = Table([[Table(left,colWidths=[288]),Table(sign_rows,colWidths=[234])]],colWidths=[304,250])
    bottom.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.5,BORDER),("LINEBEFORE",(1,0),(1,0),.5,BORDER),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [KeepTogether(bottom),Spacer(1,8),HRFlowable(width="100%",thickness=.4,color=BORDER,spaceAfter=4)]
    footer = f"This is a computer-generated invoice and does not require a physical signature. For queries, contact {_s(seller.get('email'),'support@luviio.in')} | {website}"
    if _s(seller.get("gstin")): footer += f"   GSTIN: {_s(seller.get('gstin'))}"
    story.append(Paragraph(footer,ST["foot"]))
    doc.build(story)
    return buf.getvalue()
