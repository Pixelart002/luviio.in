"""
PDF Invoice — Production Grade (Luviio SSOT)
============================================
Path: app/utils/documents/pdf_invoice.py

Clean, User-Friendly GST-compliant Tax Invoice with Giant Scannable QR Code.

Architecture Upgrades:
  ✅ Gross Amt Column — Strictly pulls 'compare_price' from API payload (Zero snapshot fallbacks).
  ✅ Direct Discount Math — Strictly calculated as (Gross Amt - Net Amt) for 100% pixel-perfect accuracy.
  ✅ Transparent Summary — Price Summary explicitly shows Subtotal + Shipping + Tax = Grand Total.
  ✅ Pure Decimal Precision — Zero floating-point discrepancies across item totals and ledger summaries.
"""
from __future__ import annotations

import io
import os
import logging
import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  SELLER CONFIG — 100% from environment variables
# ══════════════════════════════════════════════════════════════════════════════

_S = {
    "name":    os.environ.get("SELLER_LEGAL_NAME",  "Luviio Commerce"),
    "addr1":   os.environ.get("SELLER_ADDRESS_1",   "India"),
    "addr2":   os.environ.get("SELLER_ADDRESS_2",   ""),
    "state":   os.environ.get("SELLER_STATE_CODE",  "DL"),
    "pan":     os.environ.get("SELLER_PAN",         ""),
    "gstin":   os.environ.get("SELLER_GSTIN",       ""),
    "email":   os.environ.get("SELLER_EMAIL",       "support@luviio.in"),
    "website": os.environ.get("SELLER_WEBSITE",     "luviio.in"),
}

_TWO_DEC = Decimal("0.01")
_ZERO = Decimal("0.00")


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _safe(val: Any, default: str = "") -> str:
    if val is None:
        return default
    s = str(val).strip()
    return s if s and s.lower() not in ("none", "null") else default


def _dec(val: Any, default: str = "0.00") -> Decimal:
    if val is None:
        return Decimal(default)
    try:
        return Decimal(str(val)).quantize(_TWO_DEC, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _fmt(amount: Any) -> str:
    try:
        val = _dec(amount)
        return f"Rs. {val:,.2f}"
    except Exception:
        return "Rs. 0.00"


def _short_id(uuid_str: str) -> str:
    s = _safe(uuid_str)
    if s.startswith("ORD-"):
        return s
    return s[:12].upper() if len(s) >= 8 else (s.upper() or "—")


def _parse_date(dt_str: str) -> str:
    if not dt_str:
        return datetime.datetime.now().strftime("%d-%m-%Y")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S+00:00", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(dt_str[:26], fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return dt_str[:10]


def _product_name(item: dict) -> str:
    for key in ("product_name", "name", "title"):
        val = _safe(item.get(key))
        if val:
            return val
    for rel in ("products", "product", "item"):
        obj = item.get(rel)
        if isinstance(obj, dict):
            val = _safe(obj.get("name") or obj.get("product_name"))
            if val:
                return val
    return "Product Item"


def _product_hsn(item: dict) -> str:
    for key in ("hsn_code", "hsn", "hsn_sac"):
        val = _safe(item.get(key))
        if val:
            return val
    for rel in ("products", "product", "item"):
        obj = item.get(rel)
        if isinstance(obj, dict):
            val = _safe(obj.get("hsn_code") or obj.get("hsn"))
            if val:
                return val
    return "9988"


def _product_gst(item: dict) -> Decimal:
    for key in ("gst_percentage", "gst_pct", "tax_rate"):
        val = item.get(key)
        if val is not None:
            try:
                return Decimal(str(val)).quantize(_TWO_DEC)
            except (InvalidOperation, ValueError, TypeError):
                pass
    for rel in ("products", "product", "item"):
        obj = item.get(rel)
        if isinstance(obj, dict):
            val = obj.get("gst_percentage") or obj.get("gst_pct")
            if val is not None:
                try:
                    return Decimal(str(val)).quantize(_TWO_DEC)
                except (InvalidOperation, ValueError, TypeError):
                    pass
    return Decimal("18.00")


def _product_compare_price(item: dict) -> Decimal:
    """Strictly extracts compare_price from direct item or nested product relation."""
    val = item.get("compare_price")
    if val is not None:
        try:
            return Decimal(str(val)).quantize(_TWO_DEC)
        except (InvalidOperation, ValueError, TypeError):
            pass
    for rel in ("products", "product", "item"):
        obj = item.get(rel)
        if isinstance(obj, dict):
            val = obj.get("compare_price")
            if val is not None:
                try:
                    return Decimal(str(val)).quantize(_TWO_DEC)
                except (InvalidOperation, ValueError, TypeError):
                    pass
    return _ZERO


def _product_selling_price(item: dict) -> Decimal:
    """Strictly extracts price from direct item or nested product relation."""
    for key in ("price", "unit_price", "subtotal"):
        val = item.get(key)
        if val is not None:
            try:
                return Decimal(str(val)).quantize(_TWO_DEC)
            except (InvalidOperation, ValueError, TypeError):
                pass
    for rel in ("products", "product", "item"):
        obj = item.get(rel)
        if isinstance(obj, dict):
            val = obj.get("price")
            if val is not None:
                try:
                    return Decimal(str(val)).quantize(_TWO_DEC)
                except (InvalidOperation, ValueError, TypeError):
                    pass
    return _ZERO


def _create_qr(data: str, size: float = 148.0) -> Drawing:
    qr_widget = QrCodeWidget(data, barLevel='L')
    bounds = qr_widget.getBounds()
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    drawing = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
    drawing.add(qr_widget)
    return drawing


_STATE_MAP: dict[str, str] = {
    "andhra pradesh": "AP", "ap": "AP", "assam": "AS", "bihar": "BR", "chandigarh": "CH", "delhi": "DL", "new delhi": "DL", "goa": "GA", "gujarat": "GJ", "haryana": "HR", "himachal pradesh": "HP", "jharkhand": "JH", "karnataka": "KA", "kerala": "KL", "madhya pradesh": "MP", "maharashtra": "MH", "odisha": "OD", "puducherry": "PY", "punjab": "PB", "rajasthan": "RJ", "sikkim": "SK", "tamil nadu": "TN", "telangana": "TS", "tripura": "TR", "uttar pradesh": "UP", "uttarakhand": "UK", "west bengal": "WB",
}

def _state_code(raw: str) -> str:
    return _STATE_MAP.get(raw.strip().lower(), raw.strip().upper()[:2])

def _resolve_tax_type(shipping_state: str) -> str:
    if not shipping_state:
        return "IGST"
    return "CGST+SGST" if _state_code(shipping_state) == _state_code(_S["state"]) else "IGST"


# ══════════════════════════════════════════════════════════════════════════════
#  AMOUNT IN WORDS (Indian English)
# ══════════════════════════════════════════════════════════════════════════════

def _n2w(n: int) -> str:
    _ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    _TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    if n == 0: return ""
    if n < 20: return _ONES[n] + " "
    if n < 100: return _TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "") + " "
    if n < 1_000: return _ONES[n // 100] + " Hundred " + _n2w(n % 100)
    if n < 100_000: return _n2w(n // 1_000) + "Thousand " + _n2w(n % 1_000)
    if n < 10_000_000: return _n2w(n // 100_000) + "Lakh " + _n2w(n % 100_000)
    return _n2w(n // 10_000_000) + "Crore " + _n2w(n % 10_000_000)

def _amount_in_words(amount: Decimal) -> str:
    try:
        val = amount.quantize(_TWO_DEC)
        rupees = int(val)
        paise = int(round((val - Decimal(rupees)) * 100))
        parts = []
        if rupees:
            parts.append(_n2w(rupees).strip() + " Rupees")
        if paise:
            parts.append(_n2w(paise).strip() + " Paise")
        return (" and ".join(parts) + " Only") if parts else "Zero Rupees Only"
    except Exception:
        return "Amount as per invoice"


# ══════════════════════════════════════════════════════════════════════════════
#  REPORTLAB STYLES
# ══════════════════════════════════════════════════════════════════════════════

_GRAY_BG  = colors.HexColor("#f2f2f2")
_ROW_ALT  = colors.HexColor("#fafafa")
_TOTAL_BG = colors.HexColor("#e8e8e8")
_BORDER_C = colors.HexColor("#bbbbbb")
_GOLD     = colors.HexColor("#c9a96e")
_TEXT_DIM = colors.HexColor("#555555")

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    def _s(name: str, **kw) -> ParagraphStyle: return ParagraphStyle(name, parent=base, **kw)
    return {
        "logo":    _s("logo", fontName="Helvetica-Bold", fontSize=20, leading=24),
        "doc_h":   _s("doc_h", fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=TA_RIGHT),
        "doc_sub": _s("doc_sub", fontSize=7, alignment=TA_RIGHT, textColor=_TEXT_DIM, leading=10),
        "site":    _s("site", fontSize=7, textColor=_TEXT_DIM, leading=10),
        "lbl":     _s("lbl", fontName="Helvetica-Bold", fontSize=8, leading=11),
        "lbl_c":   _s("lbl_c", fontName="Helvetica-Bold", fontSize=7.5, leading=10, alignment=TA_CENTER, textColor=_TEXT_DIM),
        "b":       _s("b", fontSize=7.5, leading=10),
        "bb":      _s("bb", fontName="Helvetica-Bold", fontSize=7.5, leading=10),
        "br":      _s("br", fontSize=7.5, leading=10, alignment=TA_RIGHT),
        "bbr":     _s("bbr", fontName="Helvetica-Bold", fontSize=7.5, leading=10, alignment=TA_RIGHT),
        "sm":      _s("sm", fontSize=6.5, leading=9, textColor=_TEXT_DIM),
        "th":      _s("th", fontName="Helvetica-Bold", fontSize=7.0, leading=9),
        "thc":     _s("thc", fontName="Helvetica-Bold", fontSize=7.0, leading=9, alignment=TA_CENTER),
        "thr":     _s("thr", fontName="Helvetica-Bold", fontSize=7.0, leading=9, alignment=TA_RIGHT),
        "td":      _s("td", fontSize=7.0, leading=9),
        "tdc":     _s("tdc", fontSize=7.0, leading=9, alignment=TA_CENTER),
        "tdr":     _s("tdr", fontSize=7.0, leading=9, alignment=TA_RIGHT),
        "sum_lbl": _s("sum_lbl", fontName="Helvetica-Bold", fontSize=8, leading=11, alignment=TA_RIGHT),
        "sum_val": _s("sum_val", fontName="Helvetica-Bold", fontSize=8, leading=11, alignment=TA_RIGHT),
        "foot":    _s("foot", fontSize=6.5, leading=9, textColor=colors.HexColor("#888888"), alignment=TA_CENTER),
        "words":   _s("words", fontName="Helvetica-Bold", fontSize=7.5, leading=10),
        "words_v": _s("words_v", fontSize=7.5, leading=10),
        "sign":    _s("sign", fontName="Helvetica-Bold", fontSize=7.5, leading=10, alignment=TA_RIGHT),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PDF BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_invoice_pdf(order: dict[str, Any], customer: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    MARGIN = 20

    order_id     = _safe(order.get("id"))
    display_ord  = _safe(order.get("order_number")) or _short_id(order_id)
    order_date   = _parse_date(_safe(order.get("created_at")))
    invoice_date = datetime.datetime.now().strftime("%d-%m-%Y")
    status_raw   = _safe(order.get("status"), "paid").upper()
    is_refund    = status_raw in ("REFUNDED", "CANCELLED")

    db_invoice_no = _safe(order.get("invoice_number"))
    if db_invoice_no and db_invoice_no.isdigit():
        now = datetime.datetime.now()
        fy_start = now.year if now.month >= 4 else now.year - 1
        fy_str = f"{str(fy_start)[2:]}-{str(fy_start+1)[2:]}"
        invoice_no = f"INV/{fy_str}/{int(db_invoice_no):05d}"
    else:
        seller_state_prefix = _S["state"][:2].upper() or "DL"
        fy_year = datetime.datetime.now().strftime("%y")
        invoice_no = db_invoice_no or f"LV{seller_state_prefix}{fy_year}{_short_id(order_id)[:6]}"

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN)
    W = 554.0
    S = _styles()
    story: list = []

    ship_cost = _dec(order.get("shipping_cost"))

    sh1 = _safe(order.get("shipping_line1"))
    sh2 = _safe(order.get("shipping_line2"))
    city = _safe(order.get("shipping_city"))
    state = _safe(order.get("shipping_state"))
    pin = _safe(order.get("shipping_postal_code"))
    ctry = _safe(order.get("shipping_country"), "IN")

    c_name  = _safe(customer.get("full_name"), "Valued Customer")
    c_email = _safe(customer.get("email"))
    c_phone = _safe(customer.get("phone"))

    tax_type = _resolve_tax_type(state or city)
    doc_type = "Refund Note / Credit Note" if is_refund else "Tax Invoice / Bill of Supply / Cash Memo"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  BLOCK 1 ── HEADER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    hdr = Table([
        [Paragraph("LUVIIO", S["logo"]), Paragraph(f"<b>{doc_type}</b>", S["doc_h"])],
        [Paragraph(_S["website"], S["site"]), Paragraph("(Original for Recipient)", S["doc_sub"])],
    ], colWidths=[W * 0.55, W * 0.45])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2)]))
    story.append(hdr)
    story.append(HRFlowable(width="100%", thickness=2.5, color=_GOLD, spaceAfter=8))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  BLOCK 2 ── HORIZONTAL GRID: [SELLER | BUYER] & [ORDER DETAILS]
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    LEFT_W = 394.0
    RIGHT_W = 160.0
    HALF_L = LEFT_W / 2.0

    seller_rows = [[Paragraph("<b>Sold By:</b>", S["lbl"])], [Paragraph(_S["name"], S["bb"])]]
    for part in [_S["addr1"], _S["addr2"]]:
        if part: seller_rows.append([Paragraph(part, S["b"])])
    if _S["email"]: seller_rows.append([Spacer(1, 2)]); seller_rows.append([Paragraph(_S["email"], S["sm"])])
    if _S["pan"]: seller_rows.append([Spacer(1, 2)]); seller_rows.append([Paragraph(f"<b>PAN:</b> {_S['pan']}", S["b"])])
    if _S["gstin"]: seller_rows.append([Paragraph(f"<b>GSTIN:</b> {_S['gstin']}", S["b"])])

    addr_parts = [p for p in [sh1, sh2, city, state, pin, ctry] if p]
    buyer_rows = [[Paragraph("<b>Shipping / Billing Address:</b>", S["lbl"])], [Paragraph(c_name, S["bb"])]]
    for part in addr_parts: buyer_rows.append([Paragraph(part, S["b"])])
    if c_phone: buyer_rows.append([Spacer(1, 2)]); buyer_rows.append([Paragraph(f"Ph: {c_phone}", S["sm"])])
    if c_email: buyer_rows.append([Paragraph(c_email, S["sm"])])

    seller_tbl = Table(seller_rows, colWidths=[HALF_L - 8.0])
    seller_tbl.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 0)]))
    buyer_tbl = Table(buyer_rows, colWidths=[HALF_L - 8.0])
    buyer_tbl.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 0)]))

    top_left_grid = Table([[seller_tbl, buyer_tbl]], colWidths=[HALF_L, HALF_L])
    top_left_grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEAFTER", (0, 0), (0, -1), 0.5, _BORDER_C), ("PADDING", (0, 0), (-1, -1), 4)]))

    tracking = _safe(order.get("tracking_number"))
    order_meta_rows = [
        [Paragraph(f"<b>Invoice No:</b> {invoice_no}", S["bb"]), Paragraph(f"<b>Invoice Date:</b> {invoice_date}", S["bb"])],
        [Paragraph(f"<b>Order No:</b> {display_ord}", S["b"]), Paragraph(f"<b>Order Date:</b> {order_date}", S["b"])],
        [Paragraph(f"<b>Status:</b> {status_raw}", S["b"]), Paragraph(f"<b>Tracking:</b> {tracking if tracking else '—'}", S["b"])],
    ]
    order_meta_tbl = Table(order_meta_rows, colWidths=[HALF_L, HALF_L])
    order_meta_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("PADDING", (0, 0), (-1, -1), 3)]))

    left_panel_tbl = Table([[top_left_grid], [HRFlowable(width="100%", thickness=0.5, color=_BORDER_C)], [order_meta_tbl]], colWidths=[LEFT_W])
    left_panel_tbl.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  BLOCK 3 ── 10-COLUMN ITEMS TABLE (Gross Amt -> Net Amt -> Tax)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    CW = [18.0, 134.0, 38.0, 52.0, 22.0, 48.0, 54.0, 56.0, 52.0, 80.0]  # Exact Sum = 554.0 pt
    
    def _h(txt): return Paragraph(txt, S["th"])
    def _hc(txt): return Paragraph(txt, S["thc"])
    def _hr(txt): return Paragraph(txt, S["thr"])
    def _d(txt): return Paragraph(str(txt), S["td"])
    def _dc(txt): return Paragraph(str(txt), S["tdc"])
    def _dr(txt): return Paragraph(str(txt), S["tdr"])

    rows = [[_hc("Sl."), _h("Description"), _hc("HSN"), _hr("Gross Amt"), _hc("Qty"), _hr("Discount"), _hr("Net Amt"), _hc("Tax Type"), _hr("Tax Amt"), _hr("Total")]]

    items = order.get("order_items") or order.get("items") or []
    
    run_net        = _ZERO
    run_tax        = _ZERO
    run_disc_total = _ZERO

    for idx, item in enumerate(items, 1):
        name = _product_name(item)
        hsn  = _product_hsn(item)
        
        # Guard: Ensure shipping charges never leak into the items table
        if "shipping" in name.lower() or hsn == "9965":
            if ship_cost == _ZERO:
                ship_cost = _dec(item.get("price") or item.get("unit_price") or item.get("subtotal"))
            continue

        gst_pct = _product_gst(item)
        try:
            qty_int = int(_dec(item.get("quantity"), "1"))
            qty = Decimal(max(1, qty_int))
        except Exception:
            qty = Decimal("1")

        # 🔥 STRICT API FIELDS ONLY: 'price' and 'compare_price'
        selling_p = _product_selling_price(item)
        compare_p = _product_compare_price(item)
        
        # Net taxable amount for this line item
        row_net = (selling_p * qty).quantize(_TWO_DEC)

        # 🔥 GROSS AMT strictly calculated from 'compare_price'
        if compare_p > selling_p:
            row_gross = (compare_p * qty).quantize(_TWO_DEC)
            row_disc  = (row_gross - row_net).quantize(_TWO_DEC)
        else:
            row_gross = row_net
            row_disc  = _ZERO

        row_tax   = (row_net * (gst_pct / Decimal("100"))).quantize(_TWO_DEC)
        row_total = (row_net + row_tax).quantize(_TWO_DEC)

        run_net        += row_net
        run_tax        += row_tax
        run_disc_total += row_disc

        display_tax_type = f"CGST+SGST ({int(gst_pct)}%)" if tax_type == "CGST+SGST" else f"IGST ({int(gst_pct)}%)"

        rows.append([
            _dc(str(idx)),
            _d(name),
            _dc(hsn),
            _dr(_fmt(row_gross)),
            _dc(str(int(qty))),
            _dr(_fmt(row_disc) if row_disc > _ZERO else "—"),
            _dr(_fmt(row_net)),
            _dc(display_tax_type),
            _dr(_fmt(row_tax)),
            _dr(_fmt(row_total)),
        ])

    # STRICT TABLE FOOTER — sums cart items only
    run_items_total = (run_net + run_tax).quantize(_TWO_DEC)
    rows.append([
        Paragraph("<b>Total</b>", S["th"]), "", "", "", "", "",
        Paragraph(f"<b>{_fmt(run_net)}</b>", S["thr"]), "",
        Paragraph(f"<b>{_fmt(run_tax)}</b>", S["thr"]),
        Paragraph(f"<b>{_fmt(run_items_total)}</b>", S["thr"]),
    ])

    grand = (run_net + ship_cost + run_tax).quantize(_TWO_DEC)

    qr_payload = f"GSTIN:{_S['gstin']}|INV:{invoice_no}|DT:{invoice_date}|DISC:{run_disc_total:.2f}|TOTAL:{grand:.2f}|ORD:{display_ord}"
    qr_drawing = _create_qr(qr_payload, size=148.0)

    qr_cell = Table([[Paragraph("<b>SCAN TO VERIFY</b>", S["lbl_c"])], [Spacer(1, 2)], [qr_drawing]], colWidths=[RIGHT_W - 8.0])
    qr_cell.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("PADDING", (0, 0), (-1, -1), 4)]))

    info_grid = Table([[left_panel_tbl, qr_cell]], colWidths=[LEFT_W, RIGHT_W])
    info_grid.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, _BORDER_C), ("LINEBEFORE", (1, 0), (1, -1), 0.5, _BORDER_C), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("PADDING", (0, 0), (-1, -1), 0)]))
    story.append(info_grid)
    story.append(Spacer(1, 10))

    items_tbl = Table(rows, colWidths=CW, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _GRAY_BG), ("LINEBELOW", (0, 0), (-1, 0), 1.0, _BORDER_C),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, _ROW_ALT]), ("BACKGROUND", (0, -1), (-1, -1), _TOTAL_BG),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, _BORDER_C), ("SPAN", (0, -1), (5, -1)),
        ("BOX", (0, 0), (-1, -1), 0.5, _BORDER_C), ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("PADDING", (0, 0), (-1, -1), 4), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 10))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  BLOCK 4 ── AMOUNT IN WORDS & TRANSPARENT PRICE SUMMARY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    words_str = _amount_in_words(grand)

    # STRICT SUMMARY: Subtotal + Shipping + Tax = Grand Total
    gst_rows = [
        [Paragraph("<b>Price Summary:</b>", S["lbl"]), Paragraph("", S["b"])],
        [Paragraph("Subtotal", S["br"]), Paragraph(_fmt(run_net), S["bbr"])],
    ]

    if ship_cost > _ZERO:
        gst_rows.append([Paragraph("Shipping", S["br"]), Paragraph(_fmt(ship_cost), S["bbr"])])
    else:
        gst_rows.append([Paragraph("Shipping", S["br"]), Paragraph("FREE", S["bbr"])])

    if tax_type == "CGST+SGST":
        half_tax = (run_tax / Decimal("2")).quantize(_TWO_DEC)
        gst_rows.append([Paragraph("CGST", S["br"]), Paragraph(_fmt(half_tax), S["bbr"])])
        gst_rows.append([Paragraph("SGST", S["br"]), Paragraph(_fmt(run_tax - half_tax), S["bbr"])])
    else:
        gst_rows.append([Paragraph("IGST", S["br"]), Paragraph(_fmt(run_tax), S["bbr"])])

    gst_rows.append([Paragraph("", S["b"]), Paragraph("", S["b"])])
    gst_rows.append([Paragraph("<b>Grand Total</b>", S["sum_lbl"]), Paragraph(f"<b>{_fmt(grand)}</b>", S["sum_val"])])
    
    if run_disc_total > _ZERO:
        gst_rows.append([Paragraph("<i>Total Discount Saved</i>", S["sm"]), Paragraph(f"<i>{_fmt(run_disc_total)}</i>", S["sm"])])

    gst_tbl = Table(gst_rows, colWidths=[150.0, 84.0])
    gst_tbl.setStyle(TableStyle([("LINEABOVE", (0, -2), (-1, -2), 0.8, _BORDER_C), ("PADDING", (0, 0), (-1, -1), 2), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    right_col_rows = [[gst_tbl], [Spacer(1, 14)], [Paragraph(f"<b>For {_S['name']}:</b>", S["sign"])], [Spacer(1, 28)], [Paragraph("<b>Authorised Signatory</b>", S["sign"])]]
    left_col_rows = [[Paragraph("<b>Amount in Words:</b>", S["words"])], [Spacer(1, 3)], [Paragraph(words_str, S["words_v"])]]

    bottom = Table([[Table(left_col_rows, colWidths=[288.0]), Table(right_col_rows, colWidths=[234.0])]], colWidths=[304.0, 250.0])
    bottom.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, _BORDER_C), ("LINEBEFORE", (1, 0), (1, 0), 0.5, _BORDER_C), ("PADDING", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(KeepTogether(bottom))
    story.append(Spacer(1, 8))

    story.append(HRFlowable(width="100%", thickness=0.4, color=_BORDER_C, spaceAfter=4))
    footer_note = f"This is a computer-generated invoice and does not require a physical signature. For queries, contact {_S['email']} | {_S['website']}"
    if _S["gstin"]: footer_note += f"    GSTIN: {_S['gstin']}"
    story.append(Paragraph(footer_note, S["foot"]))

    try:
        doc.build(story)
    except Exception as exc:
        logger.error("PDF invoice build failed: %s", exc, exc_info=True)
        raise RuntimeError(f"Invoice generation failed: {exc}") from exc

    return buf.getvalue()