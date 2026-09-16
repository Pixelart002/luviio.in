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


def _qr(data: str, size: float = 72.0) -> Drawing:
    widget = QrCodeWidget(data or "LUVIIO")
    x1, y1, x2, y2 = widget.getBounds()
    width, height = x2 - x1, y2 - y1