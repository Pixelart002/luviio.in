"""
Invoice Router
==============
GET /api/v1/orders/{order_id}/invoice

Streams a server-generated PDF invoice for a completed order.
No disk writes — PDF is built in memory and streamed.

Security:
  • Customer: can only download their OWN paid/delivered/refunded orders.
  • Admin: can download any order's invoice.
  • Pending/cancelled orders: blocked (no invoice for unpaid orders).

Frontend (3-second loading pattern):
  The frontend shows a loading spinner for at least 3 seconds (UX polish),
  then auto-downloads the blob. Example:

    async function downloadInvoice(orderId) {
      const btn = document.getElementById('invoice-btn');
      btn.disabled = true;
      btn.textContent = 'Generating…';

      const [res] = await Promise.all([
        fetch(`/api/v1/orders/${orderId}/invoice`, {
          headers: { Authorization: `Bearer ${token}` }
        }),
        new Promise(r => setTimeout(r, 3000))   // min 3s wait
      ]);

      if (!res.ok) { showError('Invoice unavailable'); return; }

      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `invoice-${orderId.slice(0, 8).toUpperCase()}.pdf`;
      a.click();
      URL.revokeObjectURL(url);

      btn.disabled = false;
      btn.textContent = 'Download Invoice';
    }

Why server-side PDF?
  If the frontend generated the PDF (jsPDF, html2canvas), anyone with DevTools
  can modify the numbers before printing. Server-side generation is the only
  tamper-proof approach — the PDF bytes come directly from the DB.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase
from app.utils.pdf_invoice import build_invoice_pdf

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Invoice"])

# Only invoiceable statuses — never issue invoices for pending/cancelled orders
_INVOICEABLE: frozenset[str] = frozenset({"paid", "shipped", "delivered", "refunded"})

# Full select including nested order_items with product join
_ORDER_SELECT = (
    "id, status, created_at, subtotal, shipping_cost, tax_amount, total_amount, "
    "notes, customer_id, "
    "shipping_line1, shipping_line2, shipping_city, shipping_state, "
    "shipping_postal_code, shipping_country, "
    "tracking_number, "
    "order_items(id, product_name, unit_price, quantity, subtotal)"
)


def _get_user_id(current: dict[str, Any]) -> str:
    profile = current.get("profile")
    if isinstance(profile, dict) and "id" in profile:
        return str(profile["id"])
    if "id" in current:
        return str(current["id"])
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")


def _is_admin(current: dict[str, Any]) -> bool:
    return current.get("profile", {}).get("role") == "admin"


def _fetch_order(sb: Any, order_id: str) -> dict[str, Any]:
    """Fetch full order from DB. Raises 404 if not found."""
    res = (
        sb.table("orders")
        .select(_ORDER_SELECT)
        .eq("id", order_id)
        .limit(1)
        .execute()
    )
    if not res or not getattr(res, "data", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return res.data[0]


def _fetch_customer(sb: Any, user_id: str) -> dict[str, Any]:
    """Fetch user profile for invoice. Returns empty dict on failure (non-fatal)."""
    try:
        res = (
            sb.table("users")
            .select("email, full_name")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if res and getattr(res, "data", None):
            return res.data[0]
    except Exception as exc:
        logger.warning("_fetch_customer failed for %.8s: %s", user_id, exc)
    return {}


# ── GET /api/v1/orders/{order_id}/invoice ─────────────────────────────────────

@router.get("/orders/{order_id}/invoice")
def download_invoice(
    order_id: UUID,
    current:  dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download a PDF invoice for an order.

    Customers  : own paid/shipped/delivered/refunded orders only.
    Admins     : any order in an invoiceable status.

    Response headers:
      Content-Type        : application/pdf
      Content-Disposition : attachment; filename="invoice-XXXXXXXX.pdf"

    The PDF is generated entirely server-side and streamed without saving
    to disk. This makes it tamper-proof — frontend cannot alter any values.
    """
    sb       = get_admin_supabase()
    user_id  = _get_user_id(current)
    oid_str  = str(order_id)
    is_admin = _is_admin(current)

    order    = _fetch_order(sb, oid_str)

    # ── Ownership check ───────────────────────────────────────────────────────
    if not is_admin and order.get("customer_id") != user_id:
        # Return 404 rather than 403 to avoid leaking order existence
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # ── Status check — no invoice for pending / cancelled orders ──────────────
    order_status = order.get("status", "")
    if order_status not in _INVOICEABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invoice not available for orders with status '{order_status}'. "
                f"Invoice is generated only after payment is confirmed."
            ),
        )

    # ── Fetch customer for PDF ────────────────────────────────────────────────
    customer_id = order.get("customer_id", "")
    customer    = _fetch_customer(sb, customer_id)

    # ── Build PDF (in memory) ─────────────────────────────────────────────────
    try:
        pdf_bytes = build_invoice_pdf(order, customer)
    except Exception as exc:
        logger.error(
            "Invoice PDF generation failed | order=%.8s | %s",
            oid_str, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate invoice. Please try again.",
        )

    filename = f"invoice-{oid_str[:8].upper()}.pdf"
    logger.info(
        "Invoice downloaded | order=%.8s user=%.8s admin=%s size=%d",
        oid_str, user_id, is_admin, len(pdf_bytes),
    )

    # ── Stream PDF bytes ──────────────────────────────────────────────────────
    import io
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length":      str(len(pdf_bytes)),
            # Prevent caching — invoice data can change (status updates)
            "Cache-Control":       "no-store, no-cache, must-revalidate",
        },
    )