"""
PDF Invoice — Production Grade (Luviio SSOT)
============================================
Path: app/utils/documents/pdf_invoice.py

Amazon.in / Meesho-style 10-column GST-compliant Tax Invoice with Top-Right QR Code.

Architecture & Upgrades:
  ✅ 100% Stateless & Dynamic — Zero synchronous DB fallbacks (No lag/freeze)
  ✅ Added HSN Code column — Dynamically fetched from product join payload
  ✅ Native Vector QR Code — Aligned perfectly with Quiet Zone margin (100% Scannable!)
  ✅ Exact 554pt Width Math — Zero Overflow Guarantee on A4 pages
  ✅ Smart GST Split — CGST + SGST vs IGST clearly separated in summary
  ✅ Smart GST Invoice Formatting — Transforms integer sequences into legal INV/26-27/00001 format
"""
from __future__ import annotations

import io
import os
import logging
import datetime
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
# 🔥 NATIVE REPORTLAB QR CODE (Zero external API or image files needed)
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
    "state":   os.environ.get("SELLER_STATE_CODE",  "DL"),   # 2-letter code
    "pan":     os.environ.get("SELLER_PAN",         ""),
    "gstin":   os.environ.get("SELLER_GSTIN",       ""),
    "email":   os.environ.get("SELLER_EMAIL",       "support@luviio.in"),
    "website": os.environ.get("SELLER_WEBSITE",     "luviio.in"),
}


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _safe(val: Any, default: str = "") -> str:
    if val is None:
        return default
    s = str(val).strip()
    return s if s and s.lower() not in ("none", "null") else default


def _safe_f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _fmt(amount: Any) -> str:
    try:
        return f"Rs. {float(amount):,.2f}"
    except (TypeError, ValueError):
        return "Rs. 0.00"


def _short_id(uuid_str: str) -> str:
    s = _safe(uuid_str)
    if s.startswith("ORD-"):
        return s
    return s[:12].upper() if len(s) >= 8 else (s.upper() or "—")


def _parse_date(dt_str: str) -> str:
    if not dt_str:
        return datetime.datetime.now().strftime("%d-%m-%Y")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
    ):
        try:
            return datetime.datetime.strptime(dt_str[:26], fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return dt_str[:10]


# 🔥 PURE MEMORY EXTRACTORS (Zero DB Fallback — Eliminates API freeze/lag)
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

    return "9988"  # E-commerce generic fallback HSN if missing from payload


def _create_qr(data: str, size: float = 54.0) -> Drawing:
    """Generates an ultra-sharp, instantly scannable vector QR Code."""
    # 🔥 FIX: barLevel='L' creates cleaner, lower-density modules that mobile phone cameras scan instantly
    qr_widget = QrCodeWidget(data, barLevel='L')
    bounds = qr_widget.getBounds()
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    drawing = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
    drawing.add(qr_widget)
    return drawing


# ══════════════════════════════════════════════════════════════════════════════
#  INDIAN STATE → CODE MAP & TAX RESOLVER
# ══════════════════════════════════════════════════════════════════════════════

_STATE_MAP: dict[str, str] = {
    "andhra pradesh": "AP", "ap": "AP", "assam": "AS", "as": "AS", "bihar": "BR", "br": "BR",
    "chandigarh": "CH", "delhi": "DL", "new delhi": "DL", "nct of delhi": "DL", "dl": "DL",
    "goa": "GA", "ga": "GA", "gujarat": "GJ", "gj": "GJ", "haryana": "HR", "hr": "HR",
    "himachal pradesh": "HP", "hp": "HP", "jharkhand": "JH", "jh": "JH",
    "karnataka": "KA", "ka": "KA", "bengaluru": "KA", "bangalore": "KA",
    "kerala": "KL", "kl": "KL", "madhya pradesh": "MP", "mp": "MP",
    "maharashtra": "MH", "mh": "MH", "mumbai": "MH", "manipur": "MN", "mn": "MN",
    "meghalaya": "ML", "ml": "ML", "mizoram": "MZ", "mz": "MZ", "nagaland": "NL", "nl": "NL",
    "odisha": "OD", "od": "OD", "puducherry": "PY", "py": "PY", "punjab": "PB", "pb": "PB",
    "rajasthan": "RJ", "rj": "RJ", "sikkim": "SK", "sk": "SK",
    "tamil nadu": "TN", "tn": "TN", "chennai": "TN", "telangana": "TS", "ts": "TS", "hyderabad": "TS",
    "tripura": "TR", "tr": "TR", "uttar pradesh": "UP", "up": "UP",
    "uttarakhand": "UK", "uk": "UK", "west bengal": "WB", "wb": "WB", "kolkata": "WB",
}


def _state_code(raw: str) -> str:
    key = raw.strip().lower()
    return _STATE_MAP.get(key, raw.strip().upper()[:2])


def _resolve_tax_type(shipping_state: str) -> str:
    if not shipping_state:
        return "IGST"
    buyer_code  = _state_code(shipping_state)
    seller_code = _state_code(_S["state"])
    return "CGST+SGST" if buyer_code == seller_code else "IGST"


# ══════════════════════════════════════════════════════════════════════════════
#  AMOUNT IN WORDS (Indian English)
# ══════════════════════════════════════════════════════════════════════════════

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS_W = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _n2w(n: int) -> str:
    if n == 0:         return ""
    if n < 20:         return _ONES[n] + " "
    if n < 100:        return _TENS_W[n // 10] + (" " + _ONES[n % 10] if n % 10 else "") + " "
    if n < 1_000:      return _ONES[n // 100] + " Hundred " + _n2w(n % 100)
    if n < 100_000:    return _n2w(n // 1_000) + "Thousand " + _n2w(n % 1_000)
    if n < 10_000_000: return _n2w(n // 100_000) + "Lakh " + _n2w(n % 100_000)
    return             _n2w(n // 10_000_000) + "Crore " + _n2w(n % 10_000_000)


def _amount_in_words(amount: float) -> str:
    try:
        rupees = int(amount)
        paise  = int(round((amount - rupees) * 100))
        parts  = []
        if rupees: parts.append(_n2w(rupees).strip() + " Rupees")
        if paise:  parts.append(_n2w(paise).strip() + " Paise")
        return (" and ".join(parts) + " Only") if parts else "Zero Rupees Only"
    except Exception:
        return "Amount as per invoice"


# ══════════════════════════════════════════════════════════════════════════════
#  REPORTLAB STYLES
# ══════════════════════════════════════════════════════════════════════════════

_GRAY_BG   = colors.HexColor("#f2f2f2")
_ROW_ALT   = colors.HexColor("#fafafa")
_TOTAL_BG  = colors.HexColor("#e8e8e8")
_BORDER_C  = colors.HexColor("#bbbbbb")
_GOLD      = colors.HexColor("#c9a96e")
_TEXT_DIM  = colors.HexColor("#555555")
_TEXT_LIGHT= colors.HexColor("#888888")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]

    def _s(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, parent=base, **kw)

    return {
        "logo":     _s("logo",     fontName="Helvetica-Bold", fontSize=20, leading=24),
        "doc_h":    _s("doc_h",    fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=TA_RIGHT),
        "doc_sub":  _s("doc_sub", fontSize=7,  alignment=TA_RIGHT, textColor=_TEXT_DIM, leading=10),
        "site":     _s("site",     fontSize=7,  textColor=_TEXT_DIM, leading=10),

        "lbl":      _s("lbl",      fontName="Helvetica-Bold", fontSize=8, leading=11),

        "b":        _s("b",        fontSize=7.5, leading=10),
        "bb":       _s("bb",       fontName="Helvetica-Bold", fontSize=7.5, leading=10),
        "br":       _s("br",       fontSize=7.5, leading=10, alignment=TA_RIGHT),
        "bbr":      _s("bbr",      fontName="Helvetica-Bold", fontSize=7.5, leading=10, alignment=TA_RIGHT),
        "sm":       _s("sm",       fontSize=6.5, leading=9,  textColor=_TEXT_DIM),

        "th":       _s("th",       fontName="Helvetica-Bold", fontSize=7.0, leading=9),
        "thc":      _s("thc",      fontName="Helvetica-Bold", fontSize=7.0, leading=9, alignment=TA_CENTER),
        "thr":      _s("thr",      fontName="Helvetica-Bold", fontSize=7.0, leading=9, alignment=TA_RIGHT),
        "td":       _s("td",       fontSize=7.0, leading=9),
        "tdc":      _s("tdc",      fontSize=7.0, leading=9, alignment=TA_CENTER),
        "tdr":      _s("tdr",      fontSize=7.0, leading=9, alignment=TA_RIGHT),

        "sum_lbl":  _s("sum_lbl", fontName="Helvetica-Bold", fontSize=8, leading=11, alignment=TA_RIGHT),
        "sum_val":  _s("sum_val", fontName="Helvetica-Bold", fontSize=8, leading=11, alignment=TA_RIGHT),

        "foot":     _s("foot",     fontSize=6.5, leading=9, textColor=_TEXT_LIGHT, alignment=TA_CENTER),
        "words":    _s("words",    fontName="Helvetica-Bold", fontSize=7.5, leading=10),
        "words_v":  _s("words_v", fontSize=7.5, leading=10),
        "sign":     _s("sign",     fontName="Helvetica-Bold", fontSize=7.5, leading=10, alignment=TA_RIGHT),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PDF BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_invoice_pdf(order: dict[str, Any], customer: dict[str, Any]) -> bytes:
    buf    = io.BytesIO()
    MARGIN = 20

    # ── Extract values ────────────────────────────────────────────────────────
    order_id     = _safe(order.get("id"))
    display_ord  = _safe(order.get("order_number")) or _short_id(order_id)
    order_date   = _parse_date(_safe(order.get("created_at")))
    invoice_date = datetime.datetime.now().strftime("%d-%m-%Y")
    status_raw   = _safe(order.get("status"), "paid").upper()
    is_refund    = status_raw in ("REFUNDED", "CANCELLED")

    # 🔥 Smart GST Invoice Formatting (Transforms integer "1" -> "INV/26-27/00001")
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

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Luviio Invoice #{invoice_no}",
        author="Luviio Commerce",
        subject="Tax Invoice — GST Compliant",
        creator="Luviio Invoice System",
    )

    W = 554.0               # Explicit safe width: 595.28 - 40 = 555.28 -> anchor at 554 pt
    S = _styles()
    story: list = []

    subtotal    = _safe_f(order.get("subtotal"))
    ship_cost   = _safe_f(order.get("shipping_cost"))
    tax_amt     = _safe_f(order.get("tax_amount"))
    total_amt   = _safe_f(order.get("total_amount"))

    sh1   = _safe(order.get("shipping_line1"))
    sh2   = _safe(order.get("shipping_line2"))
    city  = _safe(order.get("shipping_city"))
    state = _safe(order.get("shipping_state"))
    pin   = _safe(order.get("shipping_postal_code"))
    ctry  = _safe(order.get("shipping_country"), "IN")

    c_name  = _safe(customer.get("full_name"), "Valued Customer")
    c_email = _safe(customer.get("email"))
    c_phone = _safe(customer.get("phone"))

    tax_type = _resolve_tax_type(state or city)
    
    shipping_is_taxed = False
    eff_rate_pct = 18

    if tax_amt > 0:
        rate_on_sub = (tax_amt / subtotal) * 100 if subtotal > 0 else 0
        diff_sub = abs(rate_on_sub - round(rate_on_sub))
        
        rate_on_both = (tax_amt / (subtotal + ship_cost)) * 100 if (subtotal + ship_cost) > 0 else 0
        diff_both = abs(rate_on_both - round(rate_on_both))

        if diff_sub <= 0.05:
            eff_rate_pct = round(rate_on_sub)
            shipping_is_taxed = False
        elif diff_both <= 0.05:
            eff_rate_pct = round(rate_on_both)
            shipping_is_taxed = True
        else:
            eff_rate_pct = round(rate_on_sub)
            shipping_is_taxed = False
    else:
        eff_rate_pct = 0
        shipping_is_taxed = False

    doc_type = (
        "Refund Note / Credit Note"
        if is_refund
        else "Tax Invoice / Bill of Supply / Cash Memo"
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  BLOCK 1 ── HEADER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    hdr = Table([
        [
            Paragraph("LUVIIO", S["logo"]),
            Paragraph(f"<b>{doc_type}</b>", S["doc_h"]),
        ],
        [
            Paragraph(_S["website"], S["site"]),
            Paragraph("(Original for Recipient)", S["doc_sub"]),
        ],
    ], colWidths=[W * 0.55, W * 0.45])
    hdr.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
    ]))
    story.append(hdr)
    story.append(HRFlowable(width="100%", thickness=2.5, color=_GOLD, spaceAfter=8))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  BLOCK 2 ── SELLER | BUYER | TOP-RIGHT QR & META  (Sum = 554 pt)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    col_w_block2 = [184.0, 185.0, 185.0]

    seller_rows = [
        [Paragraph("<b>Sold By:</b>", S["lbl"])],
        [Paragraph(_S["name"], S["bb"])],
    ]
    for part in [_S["addr1"], _S["addr2"]]:
        if part:
            seller_rows.append([Paragraph(part, S["b"])])
    if _S["email"]:
        seller_rows.append([Spacer(1, 3)])
        seller_rows.append([Paragraph(_S["email"], S["sm"])])
    if _S["pan"]:
        seller_rows.append([Spacer(1, 3)])
        seller_rows.append([Paragraph(f"<b>PAN:</b> {_S['pan']}", S["b"])])
    if _S["gstin"]:
        seller_rows.append([Paragraph(f"<b>GSTIN:</b> {_S['gstin']}", S["b"])])

    addr_parts = [p for p in [sh1, sh2, city, state, pin, ctry] if p]
    buyer_rows = [
        [Paragraph("<b>Shipping / Billing Address:</b>", S["lbl"])],
        [Paragraph(c_name, S["bb"])],
    ]
    for part in addr_parts:
        buyer_rows.append([Paragraph(part, S["b"])])
    if c_phone:
        buyer_rows.append([Spacer(1, 3)])
        buyer_rows.append([Paragraph(f"Ph: {c_phone}", S["sm"])])
    if c_email:
        buyer_rows.append([Paragraph(c_email, S["sm"])])

    tracking = _safe(order.get("tracking_number"))
    grand_for_qr = total_amt if total_amt > 0 else (subtotal + ship_cost + tax_amt)

    # 🔥 TOP-RIGHT QR CODE PAYLOAD
    qr_payload = f"GSTIN:{_S['gstin']}|INV:{invoice_no}|DT:{invoice_date}|TOTAL:{grand_for_qr:.2f}|ORD:{display_ord}"
    qr_drawing = _create_qr(qr_payload, size=54.0)

    # Split order meta and QR Code side-by-side inside the 3rd panel
    meta_text_rows = [
        [Paragraph("<b>Order Details:</b>", S["lbl"])],
        [Paragraph(f"<b>Order No:</b> {display_ord}", S["b"])],
        [Paragraph(f"<b>Order Date:</b> {order_date}", S["b"])],
        [Spacer(1, 2)],
        [Paragraph(f"<b>Invoice No:</b> {invoice_no}", S["b"])],
        [Paragraph(f"<b>Invoice Date:</b> {invoice_date}", S["b"])],
        [Spacer(1, 2)],
        [Paragraph(f"<b>Status:</b> {status_raw}", S["b"])],
    ]
    if tracking:
        meta_text_rows.append([Spacer(1, 2)])
        meta_text_rows.append([Paragraph(f"<b>Tracking:</b> {tracking}", S["b"])])

    meta_text_tbl = Table(meta_text_rows, colWidths=[110.0])
    meta_text_tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))

    # 🔥 FIX: Adjusted column widths and added explicit Quiet Zone padding around QR Code cell (1, 0)
    meta_combined_tbl = Table([[meta_text_tbl, qr_drawing]], colWidths=[110.0, 62.0])
    meta_combined_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 0), (1, 0),   "CENTER"),
        ("TOPPADDING",    (1, 0), (1, 0),   3),
        ("BOTTOMPADDING", (1, 0), (1, 0),   3),
        ("LEFTPADDING",   (1, 0), (1, 0),   4),
        ("RIGHTPADDING",  (1, 0), (1, 0),   2),
        ("TOPPADDING",    (0, 0), (0, 0),   0),
        ("BOTTOMPADDING", (0, 0), (0, 0),   0),
        ("LEFTPADDING",   (0, 0), (0, 0),   0),
    ]))

    def _panel(content_table, cw: float) -> Table:
        t = Table([[content_table]], colWidths=[cw - 12.0])
        t.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        return t

    seller_tbl = Table(seller_rows, colWidths=[col_w_block2[0] - 12.0])
    seller_tbl.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 0)]))

    buyer_tbl = Table(buyer_rows, colWidths=[col_w_block2[1] - 12.0])
    buyer_tbl.setStyle(TableStyle([("PADDING", (0, 0), (-1, -1), 0)]))

    info = Table(
        [[
            _panel(seller_tbl,        col_w_block2[0]),
            _panel(buyer_tbl,         col_w_block2[1]),
            _panel(meta_combined_tbl, col_w_block2[2]),
        ]],
        colWidths=col_w_block2,
    )
    info.setStyle(TableStyle([
        ("BOX",            (0, 0), (-1, -1), 0.5, _BORDER_C),
        ("LINEBEFORE",    (1, 0), (1, 0),   0.5, _BORDER_C),
        ("LINEBEFORE",    (2, 0), (2, 0),   0.5, _BORDER_C),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(info)
    story.append(Spacer(1, 10))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  BLOCK 3 ── 10-COLUMN ITEMS TABLE WITH HSN (Exact Sum = 554 pt)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    CW = [18.0, 136.0, 38.0, 52.0, 22.0, 44.0, 54.0, 56.0, 54.0, 80.0]

    def _h(txt):  return Paragraph(txt, S["th"])
    def _hc(txt): return Paragraph(txt, S["thc"])
    def _hr(txt): return Paragraph(txt, S["thr"])
    def _d(txt):  return Paragraph(str(txt), S["td"])
    def _dc(txt): return Paragraph(str(txt), S["tdc"])
    def _dr(txt): return Paragraph(str(txt), S["tdr"])

    rows = [[
        _hc("Sl."),
        _h("Description"),
        _hc("HSN"),
        _hr("Price"),
        _hc("Qty"),
        _hr("Discount"),
        _hr("Net Amt"),
        _hc("Tax Type"),
        _hr("Tax Amt"),
        _hr("Total"),
    ]]

    items = order.get("order_items") or order.get("items") or []
    run_tax  = 0.0
    run_net  = 0.0

    for idx, item in enumerate(items, 1):
        name      = _product_name(item)
        hsn       = _product_hsn(item)
        qty       = int(_safe_f(item.get("quantity"), 1))
        unit_p    = _safe_f(item.get("unit_price") or item.get("price_snapshot") or item.get("price"))
        compare_p = _safe_f(item.get("compare_price") or (item.get("products") or {}).get("compare_price"))
        disc      = _safe_f(item.get("discount_amount") or item.get("discount"))

        if disc == 0.0 and compare_p > unit_p > 0:
            disc = round((compare_p - unit_p) * qty, 2)

        net   = _safe_f(item.get("subtotal")) or (unit_p * qty)
        i_tax = round(net * eff_rate_pct / 100, 2)
        total = net + i_tax

        run_net  += net
        run_tax  += i_tax

        display_unit_p = compare_p if (compare_p > unit_p) else unit_p
        display_tax_type = "CGST+SGST" if tax_type == "CGST+SGST" else f"IGST ({eff_rate_pct}%)"

        rows.append([
            _dc(str(idx)),
            _d(name),
            _dc(hsn),
            _dr(_fmt(display_unit_p)),
            _dc(str(qty)),
            _dr(_fmt(disc) if disc > 0 else "—"),
            _dr(_fmt(net)),
            _dc(display_tax_type),
            _dr(_fmt(i_tax)),
            _dr(_fmt(total)),
        ])

    if ship_cost > 0:
        if shipping_is_taxed:
            s_tax = round(ship_cost * eff_rate_pct / 100, 2)
            tax_type_str = "CGST+SGST" if tax_type == "CGST+SGST" else f"IGST ({eff_rate_pct}%)"
        else:
            s_tax = 0.0
            tax_type_str = "-"
            
        s_tot = ship_cost + s_tax
        run_net += ship_cost
        run_tax += s_tax
        rows.append([
            _dc(""),
            Paragraph("<b>Shipping Charges</b>", S["td"]),
            _dc("9965"),
            _dr(_fmt(ship_cost)),
            _dc("1"),
            _dr("—"),
            _dr(_fmt(ship_cost)),
            _dc(tax_type_str),
            _dr(_fmt(s_tax)),
            _dr(_fmt(s_tot)),
        ])

    grand = total_amt if total_amt > 0 else (run_net + run_tax)
    rows.append([
        Paragraph("<b>Total</b>", S["th"]),
        "", "", "", "", "", "", "",
        Paragraph(f"<b>{_fmt(run_tax)}</b>", S["thr"]),
        Paragraph(f"<b>{_fmt(grand)}</b>",   S["thr"]),
    ])

    items_tbl = Table(rows, colWidths=CW, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), _GRAY_BG),
        ("LINEBELOW",      (0, 0), (-1, 0), 1.0, _BORDER_C),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, _ROW_ALT]),
        ("BACKGROUND",     (0, -1), (-1, -1), _TOTAL_BG),
        ("LINEABOVE",      (0, -1), (-1, -1), 0.8, _BORDER_C),
        ("SPAN",           (0, -1), (7, -1)),
        ("BOX",            (0, 0), (-1, -1), 0.5, _BORDER_C),
        ("INNERGRID",      (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 2),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 10))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  BLOCK 4 ── AMOUNT IN WORDS | GST SUMMARY | SIGNATORY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    words_str = _amount_in_words(grand)

    gst_rows: list[list] = [
        [Paragraph("<b>Price Summary:</b>", S["lbl"]), Paragraph("", S["b"])],
        [Paragraph("Subtotal", S["br"]),               Paragraph(_fmt(subtotal), S["bbr"])],
    ]
    if ship_cost > 0:
        gst_rows.append([Paragraph("Shipping", S["br"]), Paragraph(_fmt(ship_cost), S["bbr"])])
    else:
        gst_rows.append([Paragraph("Shipping", S["br"]), Paragraph("FREE", S["bbr"])])

    product_tax_only = round(subtotal * eff_rate_pct / 100, 2)
    display_tax = tax_amt if tax_amt > 0 else product_tax_only

    if tax_type == "CGST+SGST":
        half_rate = eff_rate_pct / 2
        half_tax  = round(display_tax / 2, 2)
        gst_rows.append([
            Paragraph(f"CGST @ {half_rate:.1f}%", S["br"]),
            Paragraph(_fmt(half_tax), S["bbr"]),
        ])
        gst_rows.append([
            Paragraph(f"SGST @ {half_rate:.1f}%", S["br"]),
            Paragraph(_fmt(half_tax), S["bbr"]),
        ])
    else:
        gst_rows.append([
            Paragraph(f"IGST @ {eff_rate_pct:.0f}%", S["br"]),
            Paragraph(_fmt(display_tax), S["bbr"]),
        ])

    gst_rows.append([Paragraph("", S["b"]), Paragraph("", S["b"])])
    gst_rows.append([
        Paragraph("<b>Grand Total</b>", S["sum_lbl"]),
        Paragraph(f"<b>{_fmt(grand)}</b>", S["sum_val"]),
    ])

    gst_tbl = Table(gst_rows, colWidths=[150.0, 84.0])
    gst_tbl.setStyle(TableStyle([
        ("LINEABOVE",     (0, -1), (-1, -1), 0.8, _BORDER_C),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    right_col_rows = [
        [gst_tbl],
        [Spacer(1, 14)],
        [Paragraph(f"<b>For {_S['name']}:</b>", S["sign"])],
        [Spacer(1, 28)],
        [Paragraph("<b>Authorised Signatory</b>", S["sign"])],
    ]

    left_col_rows = [
        [Paragraph("<b>Amount in Words:</b>", S["words"])],
        [Spacer(1, 3)],
        [Paragraph(words_str, S["words_v"])],
    ]

    bottom = Table(
        [[
            Table(left_col_rows,  colWidths=[288.0]),
            Table(right_col_rows, colWidths=[234.0]),
        ]],
        colWidths=[304.0, 250.0],
    )
    bottom.setStyle(TableStyle([
        ("BOX",            (0, 0), (-1, -1), 0.5, _BORDER_C),
        ("LINEBEFORE",    (1, 0), (1, 0),   0.5, _BORDER_C),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(KeepTogether(bottom))
    story.append(Spacer(1, 8))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.4, color=_BORDER_C, spaceAfter=4))
    footer_note = (
        "This is a computer-generated invoice and does not require a physical signature. "
        f"For queries, contact {_S['email']} | {_S['website']}"
    )
    if _S["gstin"]:
        footer_note += f"   GSTIN: {_S['gstin']}"
    story.append(Paragraph(footer_note, S["foot"]))

    # ── Build ─────────────────────────────────────────────────────────────
    try:
        doc.build(story)
    except Exception as exc:
        logger.error("PDF invoice build failed: %s", exc, exc_info=True)
        raise RuntimeError(f"Invoice generation failed: {exc}") from exc

    return buf.getvalue()