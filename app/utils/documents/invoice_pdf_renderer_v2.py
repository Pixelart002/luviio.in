"""Production invoice PDF renderer with explicit GST and payment breakdowns."""
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
ST: dict[str, ParagraphStyle] = {}


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


_STATE_CODES = {
    "andhra pradesh": "AP", "arunachal pradesh": "AR", "assam": "AS", "bihar": "BR",
    "chhattisgarh": "CG", "goa": "GA", "gujarat": "GJ", "haryana": "HR",
    "himachal pradesh": "HP", "jharkhand": "JH", "karnataka": "KA", "kerala": "KL",
    "madhya pradesh": "MP", "maharashtra": "MH", "manipur": "MN", "meghalaya": "ML",
    "mizoram": "MZ", "nagaland": "NL", "odisha": "OD", "punjab": "PB", "rajasthan": "RJ",
    "sikkim": "SK", "tamil nadu": "TN", "telangana": "TS", "tripura": "TR", "uttar pradesh": "UP",
    "uttarakhand": "UK", "west bengal": "WB", "chandigarh": "CH", "delhi": "DL", "new delhi": "DL",
    "puducherry": "PY", "jammu and kashmir": "JK", "ladakh": "LA", "lakshadweep": "LD",
}


def _state_code(snapshot: dict[str, Any]) -> str:
    raw = _s(snapshot.get("state_code"))
    if raw:
        return raw.upper()
    state = _s(snapshot.get("state"))
    return _STATE_CODES.get(state.lower(), "") if state else ""


def _tax_type(order: dict[str, Any]) -> str:
    return _s(order.get("tax_type"), "IGST").upper().replace("CGST_SGST", "CGST+SGST").replace("CGST/SGST", "CGST+SGST")


def _payment_status(order: dict[str, Any]) -> str:
    raw = _s(order.get("payment_status")) or _s(order.get("payment_state")) or _s(order.get("status"))
    value = raw.lower()
    mapping = {
        "succeeded": "PAID",
        "paid": "PAID",
        "pending": "PENDING",
        "processing": "PROCESSING",
        "failed": "FAILED",
        "refunded": "REFUNDED",
        "cancelled": "CANCELLED",
        "canceled": "CANCELLED",
        "requires_action": "ACTION REQUIRED",
        "requires_payment_method": "PAYMENT REQUIRED",
    }
    return mapping.get(value, raw.upper() if raw else "PENDING")


def _qr(data: str, size: float = 72.0) -> Drawing:
    widget = QrCodeWidget(data or "LUVIIO")
    x1, y1, x2, y2 = widget.getBounds()
    width, height = x2 - x1, y2 - y1
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(widget)
    return drawing


def _remote_asset(url: str, *, max_bytes: int = 2 * 1024 * 1024) -> bytes | None:
    value = _s(url)
    if not value:
        return None
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
    if not data:
        return None
    image = Image(io.BytesIO(data), width=width, height=height)
    image.hAlign = "CENTER"
    image._restrictSize(width, height)
    return image


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
        "body": st("body", fontSize=7.2, leading=9.2),
        "body_b": st("body_b", fontName="Helvetica-Bold", fontSize=7.2, leading=9.2),
        "small": st("small", fontSize=6.3, leading=8.2, textColor=DIM),
        "head": st("head", fontName="Helvetica-Bold", fontSize=6.3, leading=7.5, alignment=TA_CENTER),
        "head_l": st("head_l", fontName="Helvetica-Bold", fontSize=6.3, leading=7.5, alignment=TA_LEFT),
        "head_r": st("head_r", fontName="Helvetica-Bold", fontSize=6.3, leading=7.5, alignment=TA_RIGHT),
        "cell": st("cell", fontSize=6.4, leading=8.2),
        "cell_c": st("cell_c", fontSize=6.4, leading=8.2, alignment=TA_CENTER),
        "cell_r": st("cell_r", fontSize=6.4, leading=8.2, alignment=TA_RIGHT),
        "cell_b": st("cell_b", fontName="Helvetica-Bold", fontSize=6.4, leading=8.2),
        "sum_l": st("sum_l", fontSize=7.4, leading=9.5, alignment=TA_RIGHT),
        "sum_v": st("sum_v", fontName="Helvetica-Bold", fontSize=7.4, leading=9.5, alignment=TA_RIGHT),
        "words": st("words", fontSize=7.3, leading=9.5),
        "sign": st("sign", fontSize=7.2, leading=9.2, alignment=TA_RIGHT),
        "foot": st("foot", fontSize=6.1, leading=7.5, alignment=TA_CENTER, textColor=LIGHT),
        "section": st("section", fontName="Helvetica-Bold", fontSize=8, leading=10),
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
    if paise == 100:
        rupees, paise = rupees + 1, 0
    parts = []
    if rupees: parts.append(n2w(rupees).strip() + " Rupees")
    if paise: parts.append(n2w(paise).strip() + " Paise")
    return (" and ".join(parts) + " Only") if parts else "Zero Rupees Only"


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
        if value:
            rows.append([Paragraph(value, ST["body"])])
    if _s(p.get("phone")):
        rows += [[Spacer(1, 2)], [Paragraph(f"Ph: {_s(p.get('phone'))}", ST["small"])]]
    if _s(p.get("email")):
        rows.append([Paragraph(_s(p.get("email")), ST["small"])])
    return rows


def _line_tax(item: dict[str, Any], rate: float) -> float:
    tax = _f(item.get("tax_amount"))
    if tax <= 0 and rate > 0:
        net = _f(item.get("taxable_value"), _f(item.get("subtotal")))
        tax = round(net * rate / 100, 2)
    return max(0.0, tax)


def _split_tax(tax_amount: float, tax_type: str) -> tuple[float, float, float]:
    if tax_type == "CGST+SGST":
        cgst = round(tax_amount / 2, 2)
        return cgst, round(tax_amount - cgst, 2), 0.0
    return 0.0, 0.0, round(tax_amount, 2)


def build_snapshot_invoice_pdf(invoice_order: dict[str, Any], customer: dict[str, Any], seller_snapshot: dict[str, Any], billing_snapshot: dict[str, Any], shipping_snapshot: dict[str, Any]) -> bytes:
    global ST
    ST = _styles()
    order = invoice_order or {}
    seller = seller_snapshot or {}
    billing = billing_snapshot or {}
    shipping = shipping_snapshot or {}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN, title=f"Luviio Invoice #{_s(order.get('invoice_number'))}")
    story: list[Any] = []

    invoice_no = _s(order.get("invoice_number")) or "—"
    order_no = _s(order.get("order_number")) or _s(order.get("id")) or "—"
    payment = _payment_status(order)
    website = _s(seller.get("website"), "https://luviio.in")
    seller_name = _s(seller.get("legal_name"), _s(seller.get("brand_name"), "LUVIIO"))
    tax_type = _tax_type(order)

    logo = _asset_image(seller.get("logo_url"), 98, 42)
    hdr = Table([[logo or Paragraph("LUVIIO", ST["logo"]), Paragraph("TAX INVOICE", ST["title"])], [Paragraph(website, ST["site"]), Paragraph("Original for Recipient", ST["small_right"])]], colWidths=[W * .58, W * .42])
    hdr.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "BOTTOM"), ("BOTTOMPADDING", (0,0), (-1,-1), 2), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0)]))
    story += [hdr, HRFlowable(width="100%", thickness=2.0, color=GOLD, spaceAfter=7)]

    seller_rows = [[Paragraph("Sold By:", ST["label"])], [Paragraph(seller_name, ST["body_b"])]]
    for key in ("address_1", "address_2", "city", "district", "state", "pincode", "country"):
        value = _s(seller.get(key))
        if value:
            seller_rows.append([Paragraph(value, ST["body"])])
    if _s(seller.get("email")):
        seller_rows += [[Spacer(1, 2)], [Paragraph(_s(seller.get("email")), ST["small"])]]
    if _s(seller.get("pan")):
        seller_rows.append([Paragraph(f"<b>PAN:</b> {_s(seller.get('pan'))}", ST["body"])])
    if _s(seller.get("gstin")):
        seller_rows.append([Paragraph(f"<b>GSTIN:</b> {_s(seller.get('gstin'))}", ST["body"])])

    billing_rows = [[Paragraph("Billed To:", ST["label"])]] + _address_rows(billing, _s(customer.get("full_name"), "Valued Customer"))
    shipping_rows = [[Paragraph("Shipped To:", ST["label"])]] + _address_rows(shipping, _s(customer.get("full_name"), "Valued Customer"))

    def panel(rows: list[list[Any]], width: float) -> Table:
        t = Table(rows, colWidths=[width - 12])
        t.setStyle(TableStyle([("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0), ("TOPPADDING", (0,0), (-1,-1), 1), ("BOTTOMPADDING", (0,0), (-1,-1), 1)]))
        return t

    top = Table([[panel(seller_rows, 185), panel(billing_rows, 185), panel(shipping_rows, 185)]], colWidths=[185,185,185])
    top.setStyle(TableStyle([("BOX", (0,0), (-1,-1), .5, BORDER), ("LINEBEFORE", (1,0), (1,0), .5, BORDER), ("LINEBEFORE", (2,0), (2,0), .5, BORDER), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6), ("VALIGN", (0,0), (-1,-1), "TOP")]))
    story += [top, Spacer(1, 6)]

    place_state = _s(shipping.get("state"), "—")
    place_code = _state_code(shipping)
    place_of_supply = f"{place_state} ({place_code})" if place_code else place_state
    reverse_charge = _s(order.get("reverse_charge"), "No")
    order_meta = [[Paragraph("Order Details:", ST["label"])], [Paragraph(f"<b>Order No:</b> {order_no}", ST["body"])], [Paragraph(f"<b>Order Date:</b> {_date(order.get('created_at'))}", ST["body"])]]
    invoice_meta = [[Paragraph("Invoice Details:", ST["label"])], [Paragraph(f"<b>Invoice No:</b> {invoice_no}", ST["body"])], [Paragraph(f"<b>Invoice Date:</b> {_date(order.get('issued_at'), True)}", ST["body"])], [Paragraph(f"<b>Payment Status:</b> {payment}", ST["body_b"])], [Paragraph(f"<b>Tracking:</b> {_s(order.get('tracking_number'), '—')}", ST["body"])], [Paragraph(f"<b>Place of Supply:</b> {place_of_supply}", ST["body"])], [Paragraph(f"<b>Reverse Charge:</b> {reverse_charge}", ST["body"])]]
    qr_payload = _s(order.get("qr_payload")) or f"INV:{invoice_no}|ORD:{order_no}|TOTAL:{_f(order.get('total_amount')):.2f}"
    qr_cell = Table([[Paragraph("SCAN TO VERIFY", ST["head"])], [_qr(qr_payload, 68)]], colWidths=[105])
    qr_cell.setStyle(TableStyle([("ALIGN", (0,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("TOPPADDING", (0,0), (-1,-1), 1), ("BOTTOMPADDING", (0,0), (-1,-1), 1), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0)]))
    meta = Table([[panel(order_meta, 225), panel(invoice_meta, 225), qr_cell]], colWidths=[225,225,105])
    meta.setStyle(TableStyle([("BOX", (0,0), (-1,-1), .5, BORDER), ("LINEBEFORE", (1,0), (1,0), .5, BORDER), ("LINEBEFORE", (2,0), (2,0), .5, BORDER), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story += [meta, Spacer(1, 8)]

    cgst_sgst = tax_type == "CGST+SGST"
    if cgst_sgst:
        widths = [18, 137, 36, 48, 22, 45, 54, 42, 44, 44, 65]
        header = ["Sl.", "Description", "HSN", "Unit Price", "Qty", "Discount", "Net Amount", "GST Rate", "CGST (Rs.)", "SGST (Rs.)", "Total (Rs.)"]
    else:
        widths = [18, 142, 38, 50, 22, 48, 56, 52, 71]
        header = ["Sl.", "Description", "HSN", "Unit Price", "Qty", "Discount", "Net Amount", "GST Rate", "Total (Rs.)"]

    rows = [[Paragraph(header[0], ST["head"]), Paragraph(header[1], ST["head_l"]), Paragraph(header[2], ST["head"]), Paragraph(header[3], ST["head_r"]), Paragraph(header[4], ST["head"]), Paragraph(header[5], ST["head_r"]), Paragraph(header[6], ST["head_r"]), Paragraph(header[7], ST["head"])] + ([Paragraph(header[8], ST["head_r"]), Paragraph(header[9], ST["head_r"]), Paragraph(header[10], ST["head_r"])] if cgst_sgst else [Paragraph(header[8], ST["head_r"])])]

    items = order.get("order_items") or []
    run_net = 0.0
    run_tax = 0.0
    breakdown: dict[tuple[str, float], dict[str, float]] = {}

    for idx, item in enumerate(items, 1):
        qty = max(1, int(_f(item.get("quantity"), 1)))
        unit = _f(item.get("unit_price"))
        compare = _f(item.get("compare_price")) or _f(item.get("compare_price_snapshot")) or _f(item.get("mrp"))
        display_unit = max(unit, compare)
        discount = max(0.0, _f(item.get("discount_amount")))
        if discount <= 0 and display_unit > unit:
            discount = (display_unit - unit) * qty
        net = _f(item.get("taxable_value"))
        if net <= 0:
            net = _f(item.get("subtotal"), unit * qty)
        rate = _f(item.get("gst_percentage"))
        item_tax = _line_tax(item, rate)
        cgst, sgst, igst = _split_tax(item_tax, tax_type)
        total = _f(item.get("line_total"), net + item_tax)
        run_net += net
        run_tax += item_tax
        hsn = _s(item.get("hsn_code"), "—")
        key = (hsn, rate)
        bucket = breakdown.setdefault(key, {"net": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "tax": 0.0})
        bucket["net"] += net
        bucket["cgst"] += cgst
        bucket["sgst"] += sgst
        bucket["igst"] += igst
        bucket["tax"] += item_tax
        common = [Paragraph(str(idx), ST["cell_c"]), Paragraph(_s(item.get("product_name"), "Product"), ST["cell"]), Paragraph(hsn, ST["cell_c"]), Paragraph(_money(display_unit), ST["cell_r"]), Paragraph(str(qty), ST["cell_c"]), Paragraph(_money(discount), ST["cell_r"]), Paragraph(_money(net), ST["cell_r"]), Paragraph(f"{rate:g}%" + ("<br/>(9% + 9%)" if cgst_sgst and rate == 18 else ""), ST["cell_c"])]
        if cgst_sgst:
            rows.append(common + [Paragraph(_money(cgst), ST["cell_r"]), Paragraph(_money(sgst), ST["cell_r"]), Paragraph(_money(total), ST["cell_r"])])
        else:
            rows.append(common + [Paragraph(_money(total), ST["cell_r"])])

    shipping_cost = _f(order.get("shipping_cost"))
    if shipping_cost > 0:
        common = [Paragraph("", ST["cell"]), Paragraph("Shipping Charges", ST["cell_b"]), Paragraph(_s(order.get("shipping_hsn"), "—"), ST["cell_c"]), Paragraph(_money(shipping_cost), ST["cell_r"]), Paragraph("1", ST["cell_c"]), Paragraph(_money(0), ST["cell_r"]), Paragraph(_money(shipping_cost), ST["cell_r"]), Paragraph("—", ST["cell_c"])]
        if cgst_sgst:
            rows.append(common + [Paragraph(_money(0), ST["cell_r"]), Paragraph(_money(0), ST["cell_r"]), Paragraph(_money(shipping_cost), ST["cell_r"])])
        else:
            rows.append(common + [Paragraph(_money(shipping_cost), ST["cell_r"])])

    subtotal = _f(order.get("subtotal"), run_net)
    tax_total = _f(order.get("tax_amount"), run_tax)
    grand = _f(order.get("total_amount"), subtotal + shipping_cost + tax_total)
    total_cgst = sum(v["cgst"] for v in breakdown.values())
    total_sgst = sum(v["sgst"] for v in breakdown.values())
    total_igst = sum(v["igst"] for v in breakdown.values())

    if cgst_sgst:
        rows.append([Paragraph("Total", ST["cell_b"]), "", "", "", "", "", Paragraph(_money(run_net), ST["head_r"]), Paragraph(f"{(tax_total / run_net * 100) if run_net else 0:g}%", ST["head"]), Paragraph(_money(total_cgst), ST["head_r"]), Paragraph(_money(total_sgst), ST["head_r"]), Paragraph(_money(grand), ST["head_r"])])
    else:
        rows.append([Paragraph("Total", ST["cell_b"]), "", "", "", "", "", Paragraph(_money(run_net), ST["head_r"]), Paragraph(f"IGST", ST["head"]), Paragraph(_money(grand), ST["head_r"])])

    items_table = Table(rows, colWidths=widths, repeatRows=1)
    items_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), HEADER), ("LINEBELOW", (0,0), (-1,0), .8, BORDER), ("ROWBACKGROUNDS", (0,1), (-1,-2), [colors.white, ALT]), ("BACKGROUND", (0,-1), (-1,-1), TOTAL), ("SPAN", (0,-1), (5,-1)), ("BOX", (0,0), (-1,-1), .5, BORDER), ("INNERGRID", (0,0), (-1,-1), .25, colors.HexColor("#dddddd")), ("TOPPADDING", (0,0), (-1,-1), 3.5), ("BOTTOMPADDING", (0,0), (-1,-1), 3.5), ("LEFTPADDING", (0,0), (-1,-1), 2), ("RIGHTPADDING", (0,0), (-1,-1), 2), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story += [items_table, Spacer(1, 7)]

    gst_heading = "GST BREAKDOWN — CGST + SGST (18% = 9% + 9%)" if cgst_sgst else "GST BREAKDOWN — IGST"
    gst_rows = [[Paragraph(gst_heading, ST["section"])]]
    gst_header = [Paragraph("HSN", ST["head"]), Paragraph("Taxable Value (Rs.)", ST["head_r"]), Paragraph("GST Rate", ST["head"]), Paragraph("CGST (Rs.)", ST["head_r"]), Paragraph("SGST (Rs.)", ST["head_r"]), Paragraph("Total GST (Rs.)", ST["head_r"])] if cgst_sgst else [Paragraph("HSN", ST["head"]), Paragraph("Taxable Value (Rs.)", ST["head_r"]), Paragraph("GST Rate", ST["head"]), Paragraph("IGST (Rs.)", ST["head_r"]), Paragraph("Total GST (Rs.)", ST["head_r"])]
    gst_rows.append(gst_header)
    for (hsn, rate), bucket in sorted(breakdown.items()):
        if cgst_sgst:
            gst_rows.append([Paragraph(hsn, ST["cell_c"]), Paragraph(_money(bucket["net"]), ST["cell_r"]), Paragraph(f"{rate:g}%<br/>(9% + 9%)" if rate == 18 else f"{rate:g}%", ST["cell_c"]), Paragraph(_money(bucket["cgst"]), ST["cell_r"]), Paragraph(_money(bucket["sgst"]), ST["cell_r"]), Paragraph(_money(bucket["tax"]), ST["cell_r"])])
        else:
            gst_rows.append([Paragraph(hsn, ST["cell_c"]), Paragraph(_money(bucket["net"]), ST["cell_r"]), Paragraph(f"{rate:g}%", ST["cell_c"]), Paragraph(_money(bucket["igst"]), ST["cell_r"]), Paragraph(_money(bucket["tax"]), ST["cell_r"])])
    if cgst_sgst:
        gst_rows.append([Paragraph("Total", ST["cell_b"]), Paragraph(_money(sum(v["net"] for v in breakdown.values())), ST["cell_r"]), Paragraph("", ST["cell_c"]), Paragraph(_money(total_cgst), ST["cell_r"]), Paragraph(_money(total_sgst), ST["cell_r"]), Paragraph(_money(sum(v["tax"] for v in breakdown.values())), ST["cell_r"])])
        gst_widths = [58, 125, 80, 95, 95, 102]
    else:
        gst_rows.append([Paragraph("Total", ST["cell_b"]), Paragraph(_money(sum(v["net"] for v in breakdown.values())), ST["cell_r"]), Paragraph("", ST["cell_c"]), Paragraph(_money(total_igst), ST["cell_r"]), Paragraph(_money(sum(v["tax"] for v in breakdown.values())), ST["cell_r"])])
        gst_widths = [65, 150, 90, 120, 130]
    gst_table = Table(gst_rows, colWidths=gst_widths, repeatRows=2)
    gst_table.setStyle(TableStyle([("SPAN", (0,0), (-1,0)), ("BACKGROUND", (0,0), (-1,0), TOTAL), ("BACKGROUND", (0,1), (-1,1), HEADER), ("BACKGROUND", (0,-1), (-1,-1), TOTAL), ("BOX", (0,0), (-1,-1), .5, BORDER), ("INNERGRID", (0,1), (-1,-1), .25, colors.HexColor("#dddddd")), ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3), ("LEFTPADDING", (0,0), (-1,-1), 3), ("RIGHTPADDING", (0,0), (-1,-1), 3)]))

    summary = Table([[Paragraph("Price Summary:", ST["label"]), ""], [Paragraph("Subtotal", ST["sum_l"]), Paragraph(_money(subtotal), ST["sum_v"])], [Paragraph("Shipping", ST["sum_l"]), Paragraph(_money(shipping_cost) if shipping_cost else "FREE", ST["sum_v"])], [Paragraph("GST", ST["sum_l"]), Paragraph(_money(tax_total), ST["sum_v"])], ["", ""], [Paragraph("Grand Total", ST["sum_l"]), Paragraph(_money(grand), ST["sum_v"])]], colWidths=[150,84])
    summary.setStyle(TableStyle([("LINEABOVE", (0,-1), (-1,-1), .8, BORDER), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0), ("TOPPADDING", (0,0), (-1,-1), 2), ("BOTTOMPADDING", (0,0), (-1,-1), 2)]))

    sign_name = _s(seller.get("authorised_signatory_name"))
    sign_designation = _s(seller.get("authorised_signatory_designation"))
    signature = _asset_image(seller.get("signature_url"), 145, 45)
    sign_rows = [[Paragraph(f"<b>For {seller_name}:</b>", ST["sign"])], [Spacer(1, 4)]]
    if signature:
        sign_rows += [[signature], [Spacer(1, 2)]]
    else:
        sign_rows.append([Spacer(1, 28)])
    if sign_name:
        sign_rows.append([Paragraph(f"<b>{sign_name}</b>", ST["sign"])])
    if sign_designation:
        sign_rows.append([Paragraph(sign_designation, ST["sign"])])
    sign_rows.append([Paragraph("Authorised Signatory", ST["sign"])])

    left = [[Paragraph("Amount in Words:", ST["label"])], [Spacer(1, 2)], [Paragraph(_amount_words(grand), ST["words"])]]
    right = [[summary], [Spacer(1, 5)], *sign_rows]
    bottom = Table([[Table(left, colWidths=[288]), Table(right, colWidths=[234])]], colWidths=[304,250])
    bottom.setStyle(TableStyle([("BOX", (0,0), (-1,-1), .5, BORDER), ("LINEBEFORE", (1,0), (1,0), .5, BORDER), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7), ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP")]))

    story += [Table([[gst_table, bottom]], colWidths=[288, 250], style=TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0), ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 0)])), Spacer(1, 6), HRFlowable(width="100%", thickness=.4, color=BORDER, spaceAfter=3)]
    footer = f"This is a computer-generated invoice and does not require a physical signature. For queries, contact {_s(seller.get('email'), 'support@luviio.in')} | {website}"
    if _s(seller.get("gstin")):
        footer += f" | GSTIN: {_s(seller.get('gstin'))}"
    story.append(Paragraph(footer, ST["foot"]))
    doc.build(story)
    return buf.getvalue()
