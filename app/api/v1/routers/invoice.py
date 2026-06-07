"""
Invoice Router — Enterprise Grade
==================================
Path: app/api/v1/routers/invoice.py

Architecture Upgrades:
  1. No DTOs needed (GET request returning a raw file stream).
  2. PDF generation logic entirely decoupled into `app.utils.documents.pdf_invoice` (Facade).
  3. Database queries delegated to `OrderRepository` and `UserRepository`.
"""
from __future__ import annotations

import io
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user
from app.repositories.order_repo import OrderRepository
from app.repositories.user_repo import UserRepository
from app.utils.documents.pdf_invoice import build_invoice_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["Invoice"])

_INVOICEABLE = frozenset({"paid", "shipped", "delivered", "refunded"})

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current: dict[str, Any]) -> str:
    profile = current.get("profile", {})
    user_id = profile.get("id") or current.get("id") or current.get("sub")
    if not user_id:
        raise HTTPException(401, "User ID not found")
    return str(user_id)

def _is_admin(current: dict[str, Any]) -> bool:
    return current.get("profile", {}).get("role") == "admin"

# ══════════════════════════════════════════════════════════════════════════════
#  INVOICE ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{order_id}/invoice")
def download_invoice(
    request: Request,
    order_id: UUID,
    current: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download PDF invoice for an order.
    
    Customer: own paid/shipped/delivered/refunded orders only.
    Admin: any order in invoiceable status.
    """
    user_id = _get_user_id(current)
    oid_str = str(order_id)
    is_admin = _is_admin(current)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Invoice requested for order: {oid_str[:8]}...")
    
    # 1. Fetch data via Repositories
    order_repo = OrderRepository()
    user_repo = UserRepository()

    order = order_repo.get_order_by_id(oid_str)
    if not order:
        raise HTTPException(404, "Order not found")
        
    # 2. Verify Permissions
    if not is_admin and order.get("customer_id") != user_id:
        raise HTTPException(404, "Order not found")
        
    order_status = order.get("status", "")
    if order_status not in _INVOICEABLE:
        raise HTTPException(409, f"Invoice not available for '{order_status}' orders")
        
    if hasattr(request.state, "actions"):
        request.state.actions.append("Order permissions & status verified")
    
    # 3. Fetch Customer Details for PDF Header
    customer = user_repo.get_user_by_id(order.get("customer_id", "")) or {}
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Compiling PDF with Luviio brand standards via Facade")
        
    # 4. Generate PDF via Facade Pattern
    try:
        pdf_bytes = build_invoice_pdf(order, customer)
    except Exception as exc:
        logger.error("PDF generation failed | order=%s: %s", oid_str, exc)
        raise HTTPException(500, "Could not generate invoice")
        
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"PDF generated successfully ({len(pdf_bytes)} bytes)")
    
    filename = f"Luviio-Invoice-{oid_str[:8].upper()}.pdf"
    logger.info("Invoice downloaded | order=%s size=%d", oid_str, len(pdf_bytes))
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "Cache-Control": "no-store",
        },
    )